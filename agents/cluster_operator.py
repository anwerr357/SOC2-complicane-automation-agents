"""
agents/cluster_operator.py
──────────────────────────
Cluster Operator Agent — watches live Kubernetes cluster state.

Subscribes to
─────────────
k8s.events  — Kubernetes resource changes (mock in Week 4, real in Week 5+)

Owns controls
─────────────
CC7.1  System monitoring and alerting
CC7.2  Audit logging and monitoring
A1.1   Availability and redundancy
CC6.8  Unauthorized or malicious software protection

Difference from Policy Agent
─────────────────────────────
Policy Agent handles governance controls (CC6.x, CC9.x) — IAM, encryption.
Cluster Operator handles runtime controls (CC7.x, A1.x, CC6.8) — availability,
audit logging, unauthorized software.

Both subscribe to k8s.events but filter by control_id so they
never process each other's violations.
"""

from __future__ import annotations

import logging
import os

from agents.base_agent import BaseAgent
from brain.llm import generate_explanation
from brain.rag import retrieve_by_control_id
from store.evidence import get_session, log_event

log = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")


class ClusterOperatorAgent(BaseAgent):
    """
    Watches live Kubernetes cluster state for runtime drift.

    Detects resources modified directly (bypassing GitOps) and maps
    violations to CC7.1, CC7.2, A1.1, CC6.8.
    """

    NAME     = "cluster_operator"
    STREAMS  = ["k8s.events"]
    CONTROLS = ["CC7.1", "CC7.2", "A1.1", "CC6.8"]

    async def handle_event(self, stream: str, event: dict) -> None:
        control_id = event.get("control_id", "")

        # Only handle controls owned by this agent
        if control_id not in self.CONTROLS:
            log.debug(
                "[ClusterOperator] Skipping control %s — not owned.", control_id
            )
            return

        check_id      = event.get("check_id",      "K8S_UNKNOWN")
        control_name  = event.get("control_name",  "")
        resource_name = (
            f"{event.get('resource_kind','')}/{event.get('resource_name','')}"
        )
        namespace     = event.get("namespace", "default")
        file_path     = f"k8s/{namespace}/{event.get('resource_name','')}"
        severity      = event.get("severity",      "MEDIUM")
        violation     = event.get("violation",     "")

        log.info(
            "[ClusterOperator] Violation: %s on %s [%s]",
            check_id, resource_name, control_id,
        )

        # ── RAG ────────────────────────────────────────────────────────────
        control = await retrieve_by_control_id(control_id, QDRANT_URL)

        # ── LLM explanation ────────────────────────────────────────────────
        explanation = await generate_explanation(
            check_id=check_id,
            control_id=control_id,
            control_name=control_name,
            control_text=control.text,
            resource_name=resource_name,
            file_path=file_path,
            severity=severity,
            check_type="kubernetes",
        )

        full_description = (
            violation or
            f"{explanation.violation_summary}\n\n"
            f"{explanation.business_impact}\n\n"
            f"Remediation: {explanation.remediation_steps}"
        )

        # ── Evidence store ─────────────────────────────────────────────────
        async with get_session() as session:
            await log_event(session, {
                "agent_name":            self.NAME,
                "scanner_used":          "k8s_watch",
                "check_id":              check_id,
                "control_id":            control_id,
                "control_name":          control_name,
                "resource_name":         resource_name,
                "file_path":             file_path,
                "severity":              severity,
                "violation_description": full_description,
                "raw_finding": {
                    "check_id":       check_id,
                    "resource_kind":  event.get("resource_kind"),
                    "resource_name":  event.get("resource_name"),
                    "namespace":      namespace,
                    "change_type":    event.get("change_type"),
                    "violation":      violation,
                },
            })

        log.info(
            "[ClusterOperator] Logged violation %s/%s to evidence store.",
            control_id, check_id,
        )
