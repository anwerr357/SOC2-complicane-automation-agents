"""
agents/cluster_operator.py
──────────────────────────
Cluster Operator Agent — watches live Kubernetes cluster state for runtime drift.

Subscribes to: k8s.events
Owns controls: CC7.1, CC7.2, A1.1, CC6.8

Builds a finding dict per runtime-drift event and hands it to the shared
run_remediation_loop(). Drift has no repo file to patch, so findings are
escalated for human review.
"""
from __future__ import annotations

import logging

from agents.base_agent import BaseAgent
from agents.remediation import run_remediation_loop

log = logging.getLogger(__name__)


class ClusterOperatorAgent(BaseAgent):
    NAME = "cluster_operator"
    STREAMS = ["k8s.events"]
    CONTROLS = ["CC7.1", "CC7.2", "A1.1", "CC6.8"]

    async def handle_event(self, stream: str, event: dict) -> None:
        control_id = event.get("control_id", "")
        if control_id not in self.CONTROLS:
            log.debug("[ClusterOperator] Skipping control %s — not owned.", control_id)
            return

        namespace = event.get("namespace", "default")
        fd = {
            "agent_name": self.NAME,
            "scanner_used": "k8s_watch",
            "check_id": event.get("check_id", "K8S_UNKNOWN"),
            "control_id": control_id,
            "control_name": event.get("control_name", ""),
            "resource_name": (
                f"{event.get('resource_kind','')}/{event.get('resource_name','')}"
            ),
            "file_path": f"k8s/{namespace}/{event.get('resource_name','')}",
            "severity": event.get("severity", "MEDIUM"),
            "violation_description": event.get("violation", ""),
            "raw_finding": {
                "check_id": event.get("check_id"),
                "resource_kind": event.get("resource_kind"),
                "resource_name": event.get("resource_name"),
                "namespace": namespace,
                "change_type": event.get("change_type"),
                "violation": event.get("violation", ""),
            },
        }
        log.info(
            "[ClusterOperator] Violation: %s on %s [%s]",
            fd["check_id"], fd["resource_name"], control_id,
        )
        # Runtime drift has no repo file to patch → loop escalates for review.
        outcome = await run_remediation_loop(
            fd, repo_full_name="", github_token="",
        )
        log.info(
            "[ClusterOperator] %s/%s → %s",
            control_id, fd["check_id"], outcome.status,
        )
