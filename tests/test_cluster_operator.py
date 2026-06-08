"""ClusterOperatorAgent adapter tests — run_remediation_loop monkeypatched."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import agents.cluster_operator as co


@pytest.fixture
def captured_loop(monkeypatch):
    calls = []

    async def fake_loop(finding, *, repo_full_name, github_token):
        calls.append(finding)
        return SimpleNamespace(status="ESCALATED", pr_url=None)

    monkeypatch.setattr(co, "run_remediation_loop", fake_loop)
    return calls


@pytest.mark.asyncio
async def test_owned_event_calls_loop_as_cluster(captured_loop):
    agent = co.ClusterOperatorAgent()
    await agent.handle_event("k8s.events", {
        "control_id": "CC7.2",          # owned by Cluster
        "check_id": "K8S_NOAUDIT",
        "control_name": "Audit logging and monitoring",
        "resource_kind": "Deployment",
        "resource_name": "api",
        "namespace": "prod",
        "severity": "HIGH",
        "violation": "audit logging disabled",
    })

    assert len(captured_loop) == 1
    fd = captured_loop[0]
    assert fd["agent_name"] == "cluster_operator"
    assert fd["scanner_used"] == "k8s_watch"
    assert fd.get("repo_file_path") is None
    assert fd["control_id"] == "CC7.2"


@pytest.mark.asyncio
async def test_unowned_event_skipped(captured_loop):
    agent = co.ClusterOperatorAgent()
    await agent.handle_event("k8s.events", {
        "control_id": "CC6.7",          # owned by Policy, NOT Cluster
        "check_id": "K8S_X",
    })
    assert captured_loop == []
