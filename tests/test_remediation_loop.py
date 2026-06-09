"""Unit tests for run_remediation_loop with all I/O monkeypatched."""
from __future__ import annotations

import pytest

import agents.remediation as rem


class _FakeControl:
    control_id = "CC6.1"
    control_name = "Logical and physical access controls"
    text = "Control text from RAG."


class _FakeExplanation:
    violation_summary = "summary"
    business_impact = "impact"
    remediation_steps = "steps"


class _FakePR:
    pr_url = "https://github.com/x/y/pull/1"
    pr_number = 1
    branch = "compliance-fix/CC6-1/TRUFFLEHOG_AWS"
    patched = True
    patched_content = "PATCHED"


class _FakeEvent:
    id = "evt-123"


def _base_finding():
    return {
        "agent_name": "dev_team",
        "scanner_used": "trufflehog",
        "check_id": "TRUFFLEHOG_AWS",
        "control_id": "CC6.1",
        "control_name": "Logical and physical access controls",
        "resource_name": "AWS",
        "file_path": "config.py",
        "repo_file_path": "config.py",
        "severity": "HIGH",
        "raw_finding": {"Raw": "AKIA..."},
    }


@pytest.fixture
def patched_io(monkeypatch):
    calls = {
        "logged": None, "remediated": None,
        "escalated": None, "notified": None,
    }

    async def fake_log_event(session, finding):
        calls["logged"] = finding
        return _FakeEvent()

    async def fake_update_remediation(
        session, event_id, *, pr_url, pr_number, status=None,
        violation_description=None,
    ):
        calls["remediated"] = (event_id, pr_url, pr_number)

    async def fake_escalate(session, event_id, *, violation_description=None):
        calls["escalated"] = event_id

    class _FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def commit(self):
            pass

    def fake_get_session():
        return _FakeSession()

    async def fake_retrieve(control_id, url):
        return _FakeControl()

    async def fake_explain(**kw):
        return _FakeExplanation()

    async def fake_open_pr(**kw):
        return _FakePR()

    monkeypatch.setattr(rem, "log_event", fake_log_event)
    monkeypatch.setattr(rem, "update_remediation", fake_update_remediation)
    monkeypatch.setattr(rem, "escalate_event", fake_escalate)
    monkeypatch.setattr(rem, "get_session", fake_get_session)
    monkeypatch.setattr(rem, "retrieve_by_control_id", fake_retrieve)
    monkeypatch.setattr(rem, "generate_explanation", fake_explain)
    monkeypatch.setattr(rem, "open_remediation_pr", fake_open_pr)

    async def fake_post_escalation(**kw):
        calls["notified"] = kw
        return True

    monkeypatch.setattr(rem, "post_escalation", fake_post_escalation)
    return calls


@pytest.mark.asyncio
async def test_validation_pass_marks_remediated(patched_io, monkeypatch):
    async def fake_validate(finding, patched_content):
        return True
    monkeypatch.setattr(rem, "validate_remediation", fake_validate)

    outcome = await rem.run_remediation_loop(
        _base_finding(), repo_full_name="x/y", github_token="t"
    )
    assert outcome.status == "REMEDIATED"
    assert patched_io["remediated"] == ("evt-123", _FakePR.pr_url, 1)
    assert patched_io["escalated"] is None
    assert patched_io["notified"] is None  # no Slack on REMEDIATED


@pytest.mark.asyncio
async def test_validation_fail_escalates(patched_io, monkeypatch):
    async def fake_validate(finding, patched_content):
        return False
    monkeypatch.setattr(rem, "validate_remediation", fake_validate)

    outcome = await rem.run_remediation_loop(
        _base_finding(), repo_full_name="x/y", github_token="t"
    )
    assert outcome.status == "ESCALATED"
    assert patched_io["escalated"] == "evt-123"
    assert patched_io["remediated"] is None
    assert patched_io["notified"] is not None
    assert patched_io["notified"]["detail"] == "post-patch scan still failing"


@pytest.mark.asyncio
async def test_logs_violation_first(patched_io, monkeypatch):
    async def fake_validate(finding, patched_content):
        return True
    monkeypatch.setattr(rem, "validate_remediation", fake_validate)

    await rem.run_remediation_loop(
        _base_finding(), repo_full_name="x/y", github_token="t"
    )
    assert patched_io["logged"]["check_id"] == "TRUFFLEHOG_AWS"


@pytest.mark.asyncio
async def test_non_remediable_finding_escalates(patched_io, monkeypatch):
    """A finding with no patchable file / unsupported scanner is escalated
    without attempting a PR."""
    pr_called = {"opened": False}

    async def fake_open_pr(**kw):
        pr_called["opened"] = True
        return _FakePR()
    monkeypatch.setattr(rem, "open_remediation_pr", fake_open_pr)

    async def fake_validate(finding, patched_content):
        return True
    monkeypatch.setattr(rem, "validate_remediation", fake_validate)

    finding = _base_finding()
    finding["scanner_used"] = "k8s_watch"   # not a validate-supported scanner
    finding.pop("repo_file_path", None)
    finding["file_path"] = "k8s/default/web"

    outcome = await rem.run_remediation_loop(
        finding, repo_full_name="", github_token=""
    )
    assert outcome.status == "ESCALATED"
    assert patched_io["escalated"] == "evt-123"
    assert patched_io["remediated"] is None
    assert pr_called["opened"] is False, "must not open a PR for non-remediable findings"
    assert patched_io["notified"] is not None
    assert patched_io["notified"]["detail"] == "not auto-remediable — human review"
    assert patched_io["notified"]["control_id"] == "CC6.1"


@pytest.mark.asyncio
async def test_shallow_clone_helper(tmp_path, monkeypatch):
    """_shallow_clone clones into a temp dir without leaking the token.

    The token must NOT appear in argv (ps-readable) nor in the clone URL
    (git would persist it to .git/config). It is supplied via a GIT_ASKPASS
    helper, reading the token from the child env.
    """
    from agents.dev_team_agent import _shallow_clone

    captured = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env", {})

        class _P:
            returncode = 0
            async def communicate(self):
                return (b"", b"")
        return _P()

    secret = "ghp_SeCrEt123456"
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    dest = await _shallow_clone("owner/repo", "abc123", secret, str(tmp_path), depth=1)
    assert dest == str(tmp_path)
    assert "git" in captured["args"][0]
    assert "--depth" in captured["args"]
    # repo URL present, but WITHOUT the token embedded
    assert any("github.com/owner/repo" in a for a in captured["args"])
    assert not any(secret in a for a in captured["args"]), "token must not be in argv"
    # token is delivered via the askpass env instead
    assert captured["env"].get("GH_TOKEN") == secret
    assert "GIT_ASKPASS" in captured["env"]
