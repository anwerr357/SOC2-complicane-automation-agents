"""
agents/policy_agent.py
──────────────────────
Policy Agent — governance watcher for Terraform and Kubernetes YAML.

Subscribes to: k8s.events, tf.plans
Owns controls: CC6.1, CC6.6, CC6.7, CC9.1

Builds a finding dict per event and hands it to the shared
run_remediation_loop(). Terraform findings carry a repo_file_path
(auto-remediable → PR); K8s drift carries none (→ escalated for review).
"""
from __future__ import annotations

import logging
import os

from agents.base_agent import BaseAgent
from agents.remediation import run_remediation_loop
from scanners.checkov_runner import run_checkov

log = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_OWNER = os.environ.get("GITHUB_REPO_OWNER", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO_NAME", "")


class PolicyAgent(BaseAgent):
    NAME = "policy"
    STREAMS = ["k8s.events", "tf.plans"]
    CONTROLS = ["CC6.1", "CC6.6", "CC6.7", "CC9.1"]

    async def handle_event(self, stream: str, event: dict) -> None:
        if stream == "tf.plans":
            await self._handle_tf_plan(event)
        elif stream == "k8s.events":
            await self._handle_k8s_event(event)

    # ── Terraform plan handler ─────────────────────────────────────────────

    async def _handle_tf_plan(self, event: dict) -> None:
        file_path = event.get("file_path")
        if not file_path:
            log.warning("[PolicyAgent] tf.plans event missing file_path — skipping.")
            return

        findings = await run_checkov(file_path, git_sha=event.get("git_sha"))
        owned = [f for f in findings if f.control_id in self.CONTROLS]
        log.info(
            "[PolicyAgent] tf.plans: %d findings, %d owned.",
            len(findings), len(owned),
        )

        repo_full_name = f"{GITHUB_OWNER}/{GITHUB_REPO}"
        for finding in owned:
            fd = finding.to_evidence_dict()
            fd["repo_file_path"] = event.get("repo_file_path")
            outcome = await run_remediation_loop(
                fd, repo_full_name=repo_full_name, github_token=GITHUB_TOKEN,
            )
            log.info("[PolicyAgent] %s → %s", fd["check_id"], outcome.status)

    # ── K8s event handler ──────────────────────────────────────────────────

    async def _handle_k8s_event(self, event: dict) -> None:
        control_id = event.get("control_id", "")
        if control_id not in self.CONTROLS:
            log.debug("[PolicyAgent] Skipping control %s — not owned.", control_id)
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
                "violation": event.get("violation", ""),
            },
        }
        # K8s drift has no repo file to patch → loop escalates for human review.
        outcome = await run_remediation_loop(
            fd, repo_full_name="", github_token="",
        )
        log.info("[PolicyAgent] k8s %s → %s", fd["check_id"], outcome.status)
