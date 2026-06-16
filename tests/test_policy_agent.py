"""PolicyAgent adapter tests — run_remediation_loop and SandboxedScanRunner monkeypatched."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.policy_agent as pa


class _FakeCheckovFinding:
    def __init__(self, control_id):
        self.check_id = "CKV_AWS_145"
        self.control_id = control_id
        self.control_name = "Encryption at rest"
        self.resource_name = "aws_s3_bucket.app_data"
        self.file_path = "/tmp/scan/main.tf"
        self.severity = "MEDIUM"

    def to_evidence_dict(self):
        return {
            "agent_name": "policy",
            "scanner_used": "checkov",
            "check_id": self.check_id,
            "control_id": self.control_id,
            "control_name": self.control_name,
            "resource_name": self.resource_name,
            "file_path": self.file_path,
            "severity": self.severity,
            "violation_description": "",
            "raw_finding": {},
        }


@pytest.fixture
def captured_loop(monkeypatch):
    calls = []

    async def fake_loop(finding, *, repo_full_name, github_token):
        calls.append(finding)
        return SimpleNamespace(status="REMEDIATED", pr_url="http://x/pr/1")

    monkeypatch.setattr(pa, "run_remediation_loop", fake_loop)
    return calls


@pytest.mark.asyncio
async def test_tf_plan_owned_finding_gets_repo_file_path(captured_loop, monkeypatch):
    from scanners.sandboxed_runner import ScanResult

    fake_scan_result = ScanResult(checkov=[_FakeCheckovFinding("CC6.7"), _FakeCheckovFinding("CC8.8")])

    mock_runner_instance = AsyncMock()
    mock_runner_instance.scan_file.return_value = fake_scan_result

    with (
        patch("agents.policy_agent.SandboxedScanRunner", return_value=mock_runner_instance),
        patch("agents.policy_agent.GITHUB_OWNER", "myorg"),
        patch("agents.policy_agent.GITHUB_REPO", "myrepo"),
    ):
        agent = pa.PolicyAgent()
        await agent.handle_event("tf.plans", {
            "file_path": "/tmp/scan/main.tf",
            "repo_file_path": "infra/main.tf",
            "git_sha": "abc123",
        })

    assert len(captured_loop) == 1, "only the owned (CC6.7) finding should run the loop"
    assert captured_loop[0]["repo_file_path"] == "infra/main.tf"
    assert captured_loop[0]["control_id"] == "CC6.7"


@pytest.mark.asyncio
async def test_k8s_owned_event_has_no_repo_file_path(captured_loop):
    agent = pa.PolicyAgent()
    await agent.handle_event("k8s.events", {
        "control_id": "CC6.6",          # owned by Policy
        "check_id": "K8S_PRIV",
        "control_name": "Least privilege",
        "resource_kind": "Pod",
        "resource_name": "web",
        "namespace": "default",
        "severity": "HIGH",
        "violation": "privileged container",
    })

    assert len(captured_loop) == 1
    fd = captured_loop[0]
    assert fd.get("repo_file_path") is None
    assert fd["agent_name"] == "policy"
    assert fd["scanner_used"] == "k8s_watch"
    assert fd["control_id"] == "CC6.6"


@pytest.mark.asyncio
async def test_k8s_unowned_event_skipped(captured_loop):
    agent = pa.PolicyAgent()
    await agent.handle_event("k8s.events", {
        "control_id": "CC7.1",          # owned by Cluster, NOT Policy
        "check_id": "K8S_X",
    })
    assert captured_loop == []
