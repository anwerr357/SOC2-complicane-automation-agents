"""Unit tests for RemediationWorkflow with all I/O monkeypatched."""
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


class _FakeRunOutput:
    """Minimal stand-in for agno RunOutput when response_model is set."""
    content = _FakeExplanation()


class _FakeRecommendAgent:
    async def arun(self, message, **kwargs):
        return _FakeRunOutput()


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

    def fake_build_recommend_agent(instructions):
        return _FakeRecommendAgent()

    async def fake_open_pr(**kw):
        return _FakePR()

    async def fake_post_escalation(**kw):
        calls["notified"] = kw
        return True

    monkeypatch.setattr(rem, "log_event", fake_log_event)
    monkeypatch.setattr(rem, "update_remediation", fake_update_remediation)
    monkeypatch.setattr(rem, "escalate_event", fake_escalate)
    monkeypatch.setattr(rem, "get_session", fake_get_session)
    monkeypatch.setattr(rem, "retrieve_by_control_id", fake_retrieve)
    monkeypatch.setattr(rem, "_build_recommend_agent", fake_build_recommend_agent)
    monkeypatch.setattr(rem, "open_remediation_pr", fake_open_pr)
    monkeypatch.setattr(rem, "post_escalation", fake_post_escalation)

    return calls


@pytest.mark.asyncio
async def test_validation_pass_marks_remediated(patched_io, monkeypatch):
    async def fake_validate(finding, patched_content):
        return True

    async def fake_post_remediation(**kw):
        pass

    monkeypatch.setattr(rem, "validate_remediation", fake_validate)
    monkeypatch.setattr(rem, "post_remediation", fake_post_remediation)

    outcome = await rem.RemediationWorkflow().arun(
        _base_finding(), repo_full_name="x/y", github_token="t"
    )
    assert outcome.status == "REMEDIATED"
    assert patched_io["remediated"] == ("evt-123", _FakePR.pr_url, 1)
    assert patched_io["escalated"] is None
    assert patched_io["notified"] is None


@pytest.mark.asyncio
async def test_validation_fail_escalates(patched_io, monkeypatch):
    async def fake_validate(finding, patched_content):
        return False

    monkeypatch.setattr(rem, "validate_remediation", fake_validate)

    outcome = await rem.RemediationWorkflow().arun(
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

    async def fake_post_remediation(**kw):
        pass

    monkeypatch.setattr(rem, "validate_remediation", fake_validate)
    monkeypatch.setattr(rem, "post_remediation", fake_post_remediation)

    await rem.RemediationWorkflow().arun(
        _base_finding(), repo_full_name="x/y", github_token="t"
    )
    assert patched_io["logged"]["check_id"] == "TRUFFLEHOG_AWS"


@pytest.mark.asyncio
async def test_non_remediable_finding_escalates(patched_io, monkeypatch):
    """A finding with an unsupported scanner is escalated without opening a PR."""
    pr_called = {"opened": False}

    async def fake_open_pr(**kw):
        pr_called["opened"] = True
        return _FakePR()

    async def fake_validate(finding, patched_content):
        return True

    monkeypatch.setattr(rem, "open_remediation_pr", fake_open_pr)
    monkeypatch.setattr(rem, "validate_remediation", fake_validate)

    finding = _base_finding()
    finding["scanner_used"] = "k8s_watch"
    finding.pop("repo_file_path", None)
    finding["file_path"] = "k8s/default/web"

    outcome = await rem.RemediationWorkflow().arun(
        finding, repo_full_name="", github_token=""
    )
    assert outcome.status == "ESCALATED"
    assert patched_io["escalated"] == "evt-123"
    assert patched_io["remediated"] is None
    assert pr_called["opened"] is False
    assert patched_io["notified"] is not None
    assert patched_io["notified"]["detail"] == "not auto-remediable — human review"
    assert patched_io["notified"]["control_id"] == "CC6.1"
