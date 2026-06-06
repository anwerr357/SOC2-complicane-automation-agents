"""
agents/policy_agent.py
──────────────────────
Policy Agent — governance watcher for Terraform and Kubernetes YAML.

Subscribes to
─────────────
k8s.events  — Kubernetes resource violations (from k8s_watcher or mock)
tf.plans    — Terraform plan scan requests (file_path in event payload)

Owns controls
─────────────
CC6.1  Logical and physical access controls
CC6.6  Least privilege and logical access restriction
CC6.7  Encryption at rest
CC9.1  Risk assessment and mitigation

Remediation loop per event
──────────────────────────
1. Receive event from Redis Stream
2. RAG  → retrieve SOC 2 control text from Qdrant
3. LLM  → generate plain-English explanation
4. Store → log violation to evidence_events table
5. PR   → open remediation pull request on GitHub (if GITHUB_TOKEN set)
"""

from __future__ import annotations

import logging
import os

from agents.base_agent import BaseAgent
from brain.llm import generate_explanation
from brain.rag import retrieve_by_control_id
from mutate.mutate import open_remediation_pr
from scanners.checkov_runner import run_checkov
from store.evidence import get_session, log_event, update_remediation

log = logging.getLogger(__name__)

QDRANT_URL     = os.environ.get("QDRANT_URL",        "http://localhost:6333")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN",      "")
GITHUB_OWNER   = os.environ.get("GITHUB_REPO_OWNER", "")
GITHUB_REPO    = os.environ.get("GITHUB_REPO_NAME",  "")


class PolicyAgent(BaseAgent):
    """
    Watches governance policies across all infrastructure.

    Handles two event types:
      - k8s.events  → pre-computed violation from k8s_watcher
      - tf.plans    → file_path to scan with Checkov
    """

    NAME     = "policy"
    STREAMS  = ["k8s.events", "tf.plans"]
    CONTROLS = ["CC6.1", "CC6.6", "CC6.7", "CC9.1"]

    async def handle_event(self, stream: str, event: dict) -> None:
        if stream == "tf.plans":
            await self._handle_tf_plan(event)
        elif stream == "k8s.events":
            await self._handle_k8s_event(event)

    # ── Terraform plan handler ─────────────────────────────────────────────

    async def _handle_tf_plan(self, event: dict) -> None:
        """
        Run Checkov on the file_path from the event.
        For each finding owned by this agent, run the full remediation loop.
        """
        file_path = event.get("file_path")
        if not file_path:
            log.warning("[PolicyAgent] tf.plans event missing file_path — skipping.")
            return

        git_sha  = event.get("git_sha")
        findings = await run_checkov(file_path, git_sha=git_sha)

        # Only handle controls this agent owns
        owned = [f for f in findings if f.control_id in self.CONTROLS]
        log.info("[PolicyAgent] tf.plans: %d findings, %d owned.", len(findings), len(owned))

        for finding in owned:
            await self._remediation_loop(
                check_id=finding.check_id,
                control_id=finding.control_id,
                control_name=finding.control_name,
                resource_name=finding.resource_name,
                file_path=finding.file_path,
                severity=finding.severity,
                repo_file_path=event.get("repo_file_path"),
            )

    # ── K8s event handler ──────────────────────────────────────────────────

    async def _handle_k8s_event(self, event: dict) -> None:
        """
        Handle a pre-computed K8s violation event.
        Only process controls owned by this agent.
        """
        control_id = event.get("control_id", "")
        if control_id not in self.CONTROLS:
            log.debug(
                "[PolicyAgent] Skipping event with control %s — not owned.", control_id
            )
            return

        await self._remediation_loop(
            check_id=event.get("check_id", "K8S_UNKNOWN"),
            control_id=control_id,
            control_name=event.get("control_name", ""),
            resource_name=f"{event.get('resource_kind','')}/{event.get('resource_name','')}",
            file_path=f"k8s/{event.get('namespace','default')}/{event.get('resource_name','')}",
            severity=event.get("severity", "MEDIUM"),
            violation=event.get("violation", ""),
            repo_file_path=None,   # K8s drift — no direct file to patch
        )

    # ── Full remediation loop ──────────────────────────────────────────────

    async def _remediation_loop(
        self,
        *,
        check_id:      str,
        control_id:    str,
        control_name:  str,
        resource_name: str,
        file_path:     str,
        severity:      str,
        violation:     str = "",
        repo_file_path: str | None = None,
    ) -> None:
        """Steps 2-5 of the remediation loop for one violation."""

        # ── Step 2: RAG ────────────────────────────────────────────────────
        control = await retrieve_by_control_id(control_id, QDRANT_URL)

        # ── Step 3: LLM explanation ────────────────────────────────────────
        explanation = await generate_explanation(
            check_id=check_id,
            control_id=control_id,
            control_name=control_name,
            control_text=control.text,
            resource_name=resource_name,
            file_path=file_path,
            severity=severity,
        )

        full_description = (
            violation or
            f"{explanation.violation_summary}\n\n"
            f"{explanation.business_impact}\n\n"
            f"Remediation: {explanation.remediation_steps}"
        )

        # ── Step 4: Store ──────────────────────────────────────────────────
        async with get_session() as session:
            event_row = await log_event(session, {
                "agent_name":            self.NAME,
                "scanner_used":          "checkov",
                "check_id":              check_id,
                "control_id":            control_id,
                "control_name":          control_name,
                "resource_name":         resource_name,
                "file_path":             file_path,
                "severity":              severity,
                "violation_description": full_description,
                "raw_finding":           {
                    "check_id":      check_id,
                    "resource":      resource_name,
                    "control_id":    control_id,
                    "violation":     violation,
                },
            })

            # ── Step 5: PR ─────────────────────────────────────────────────
            if repo_file_path and GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO:
                try:
                    result = await open_remediation_pr(
                        github_token=GITHUB_TOKEN,
                        repo_full_name=f"{GITHUB_OWNER}/{GITHUB_REPO}",
                        file_path=repo_file_path,
                        check_id=check_id,
                        control_id=control_id,
                        control_name=control_name,
                        resource_name=resource_name,
                        severity=severity,
                        violation_description=explanation.violation_summary,
                        control_text=control.text,
                    )
                    await update_remediation(
                        session,
                        event_row.id,
                        pr_url=result.pr_url,
                        pr_number=result.pr_number,
                    )
                    log.info(
                        "[PolicyAgent] PR opened for %s: %s",
                        check_id, result.pr_url,
                    )
                except Exception as exc:
                    log.error("[PolicyAgent] PR failed for %s: %s", check_id, exc)
