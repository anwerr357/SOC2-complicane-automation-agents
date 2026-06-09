"""Unit tests for notify/slack.py with httpx monkeypatched (no real network)."""
from __future__ import annotations

import json

import pytest

import notify.slack as slack


def _kwargs():
    return dict(
        check_id="K8S_DRIFT",
        control_id="CC6.8",
        control_name="Unauthorized software protection",
        severity="HIGH",
        resource_name="web/nginx",
        agent_name="cluster_operator",
        explanation="explanation text about the drift",
        event_id="8f2a-1234",
        detail="not auto-remediable — human review",
    )


def test_build_blocks_contains_key_fields():
    blocks = slack._build_blocks(**_kwargs())
    flat = json.dumps(blocks)
    assert "CC6.8" in flat
    assert "HIGH" in flat
    assert "web/nginx" in flat
    assert "explanation text about the drift" in flat
    assert "8f2a-1234" in flat
    # first block is the header
    assert blocks[0]["type"] == "header"


def test_build_blocks_truncates_long_explanation():
    kw = _kwargs()
    kw["explanation"] = "x" * 5000
    blocks = slack._build_blocks(**kw)
    flat = json.dumps(blocks)
    # no single string should blow past Slack's 3000-char block limit
    assert "x" * 3001 not in flat


def _make_client(captured, response):
    """Return a fake httpx.AsyncClient class that records the POST and returns
    a response whose .json() yields `response`."""
    class _Resp:
        def json(self):
            return response

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, *, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Resp()

    return _Client


@pytest.mark.asyncio
async def test_post_escalation_happy_path(monkeypatch):
    captured = {}
    monkeypatch.setattr(slack, "SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setattr(slack, "SLACK_ALERT_CHANNEL", "#compliance-alerts")
    monkeypatch.setattr(slack.httpx, "AsyncClient",
                        _make_client(captured, {"ok": True}))

    ok = await slack.post_escalation(**_kwargs())

    assert ok is True
    assert captured["url"] == slack.SLACK_POST_URL
    assert captured["headers"]["Authorization"] == "Bearer xoxb-test"
    assert captured["json"]["channel"] == "#compliance-alerts"
    assert captured["json"]["blocks"][0]["type"] == "header"
    assert captured["json"]["text"]  # non-empty notification fallback


@pytest.mark.asyncio
async def test_post_escalation_no_token_skips(monkeypatch):
    called = {"posted": False}
    monkeypatch.setattr(slack, "SLACK_BOT_TOKEN", "")

    class _Boom:
        def __init__(self, *a, **k):
            called["posted"] = True

    monkeypatch.setattr(slack.httpx, "AsyncClient", _Boom)

    ok = await slack.post_escalation(**_kwargs())

    assert ok is False
    assert called["posted"] is False, "must not construct a client without a token"


@pytest.mark.asyncio
async def test_post_escalation_logical_error(monkeypatch):
    captured = {}
    monkeypatch.setattr(slack, "SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setattr(
        slack.httpx, "AsyncClient",
        _make_client(captured, {"ok": False, "error": "channel_not_found"}),
    )

    ok = await slack.post_escalation(**_kwargs())

    assert ok is False  # Slack returns HTTP 200 but ok=false


@pytest.mark.asyncio
async def test_post_escalation_transport_error(monkeypatch):
    monkeypatch.setattr(slack, "SLACK_BOT_TOKEN", "xoxb-test")

    class _Raising:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.ConnectError("boom")

    import httpx  # local import so the test references the same module
    monkeypatch.setattr(slack.httpx, "AsyncClient", _Raising)

    ok = await slack.post_escalation(**_kwargs())

    assert ok is False  # caught, never raised
