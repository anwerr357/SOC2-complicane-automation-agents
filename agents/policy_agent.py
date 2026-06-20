"""Policy Agent: governance watcher for Terraform and Kubernetes YAML feeding the shared remediation loop."""

from __future__ import annotations

import logging
import os

from agents.base_agent import BaseAgent
from agents.remediation import RemediationWorkflow
from scanners.sandboxed_runner import SandboxedScanRunner

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

    async def _handle_tf_plan(self, event: dict) -> None:
        repo_file_path = event.get("repo_file_path") or event.get("file_path")
        if not repo_file_path:
            log.warning("[PolicyAgent] tf.plans event missing repo_file_path — skipping.")
            return

        repo_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
        try:
            result = await SandboxedScanRunner().scan_file(
                repo_url,
                repo_file_path,
                git_sha=event.get("git_sha"),
            )
        except Exception as exc:
            log.error("[PolicyAgent] sandboxed scan_file failed: %s", exc)
            return

        owned = [f for f in result.checkov if f.control_id in self.CONTROLS]
        log.info(
            "[PolicyAgent] tf.plans: %d findings, %d owned.",
            len(result.checkov), len(owned),
        )

        repo_full_name = f"{GITHUB_OWNER}/{GITHUB_REPO}"
        for finding in owned:
            fd = finding.to_evidence_dict()
            fd["repo_file_path"] = repo_file_path
            outcome = await RemediationWorkflow().arun(
                fd, repo_full_name=repo_full_name, github_token=GITHUB_TOKEN,
            )
            log.info("[PolicyAgent] %s → %s", fd["check_id"], outcome.status)

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
        outcome = await RemediationWorkflow().arun(
            fd, repo_full_name="", github_token="",
        )
        log.info("[PolicyAgent] k8s %s → %s", fd["check_id"], outcome.status)
