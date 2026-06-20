"""Agno-instrumented 5-step remediation workflow (notify → learn → recommend → mutate → validate)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from agno.agent import Agent
from agno.models.anthropic import Claude

from brain.llm import ExplanationResult, build_system_prompt
from brain.rag import retrieve_by_control_id
from mutate.mutate import open_remediation_pr
from mutate.validate import validate_remediation
from notify.slack import post_escalation, post_remediation
from store.evidence import (
    escalate_event,
    get_session,
    log_event,
    update_remediation,
)

log = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
_CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

_VALIDATE_SUPPORTED = {"checkov", "semgrep", "trufflehog"}


@dataclass
class LoopOutcome:
    status: str            # REMEDIATED | ESCALATED | ERROR
    pr_url: str | None = None
    detail: str = ""


def _build_recommend_agent(instructions: str) -> Agent:
    """Create a fresh agno Agent for the RECOMMEND step.

    A new Agent is created per workflow run so dynamic instructions
    (which embed the per-finding control text) never race between
    concurrent runs. The Anthropic-side prompt cache is keyed by
    content, not by Python object identity, so cache hits still occur
    when two consecutive findings share the same control.
    """
    return Agent(
        name="SOC2-Recommend",
        model=Claude(
            id=_CLAUDE_MODEL,
            cache_system_prompt=True,
            async_client=AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY")),
        ),
        response_model=ExplanationResult,
        instructions=instructions,
    )


def _build_user_message(
    *,
    check_id: str,
    control_id: str,
    control_name: str,
    resource_name: str,
    file_path: str,
    severity: str,
) -> str:
    return (
        f"Explain the following SOC 2 violation:\n\n"
        f"- **Check ID:** {check_id}\n"
        f"- **Resource:** `{resource_name}`\n"
        f"- **File:** `{file_path}`\n"
        f"- **Severity:** {severity}\n\n"
        f"The resource `{resource_name}` failed check `{check_id}`, "
        f"which maps to SOC 2 criterion **{control_id} ({control_name})**."
    )


class RemediationWorkflow:
    """Agno-instrumented 5-step compliance remediation loop.

    Every call to arun() traces the RECOMMEND (LLM) step to Langfuse
    automatically when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY /
    LANGFUSE_HOST are set. The session_id on the agent call equals the
    Postgres event_id, enabling cross-reference between Langfuse and
    the evidence store.
    """

    async def arun(
        self,
        finding: dict,
        *,
        repo_full_name: str,
        github_token: str,
    ) -> LoopOutcome:
        """Run steps 1–5 for a single finding. Never raises."""
        check_id = finding.get("check_id", "?")
        control_id = finding.get("control_id", "CC0.0")

        try:
            async with get_session() as session:
                event = await log_event(session, finding)
            event_id = event.id

            # 2 LEARN ---------------------------------------------------------
            control = await retrieve_by_control_id(control_id, QDRANT_URL)

            control_name = finding.get("control_name", control.control_name)
            instructions = build_system_prompt(control.text, control_id, control_name)
            user_message = _build_user_message(
                check_id=check_id,
                control_id=control_id,
                control_name=control_name,
                resource_name=finding.get("resource_name", "unknown"),
                file_path=finding.get("file_path", "unknown"),
                severity=finding.get("severity", "MEDIUM"),
            )
            recommend_agent = _build_recommend_agent(instructions)
            result = await recommend_agent.arun(user_message, session_id=str(event_id))
            explanation: ExplanationResult = result.content

            enriched = (
                f"{explanation.violation_summary}\n\n"
                f"{explanation.business_impact}\n\n"
                f"Remediation: {explanation.remediation_steps}"
            )

            patch_path = finding.get("repo_file_path") or finding.get("file_path")
            remediable = bool(
                repo_full_name
                and github_token
                and patch_path
                and finding.get("scanner_used") in _VALIDATE_SUPPORTED
            )

            if not remediable:
                async with get_session() as session:
                    await escalate_event(session, event_id, violation_description=enriched)
                await post_escalation(
                    check_id=check_id,
                    control_id=control_id,
                    control_name=control_name,
                    severity=finding.get("severity", "MEDIUM"),
                    resource_name=finding.get("resource_name", "unknown"),
                    agent_name=finding.get("agent_name", "unknown"),
                    explanation=enriched,
                    event_id=str(event_id),
                    detail="not auto-remediable — human review",
                )
                log.warning("[workflow] %s not auto-remediable → escalated", check_id)
                return LoopOutcome(
                    status="ESCALATED",
                    detail="not auto-remediable — human review",
                )

            pr = await open_remediation_pr(
                github_token=github_token,
                repo_full_name=repo_full_name,
                file_path=patch_path,
                check_id=check_id,
                control_id=control_id,
                control_name=control_name,
                resource_name=finding.get("resource_name", "unknown"),
                severity=finding.get("severity", "MEDIUM"),
                violation_description=explanation.violation_summary,
                control_text=control.text,
            )

            # 5 VALIDATE -----------------------------------------------------
            ok = await validate_remediation(finding, pr.patched_content)
            async with get_session() as session:
                if ok:
                    await update_remediation(
                        session, event_id,
                        pr_url=pr.pr_url,
                        pr_number=pr.pr_number,
                        violation_description=enriched,
                    )
                    await post_remediation(
                        check_id=check_id,
                        control_id=control_id,
                        control_name=control_name,
                        severity=finding.get("severity", "MEDIUM"),
                        resource_name=finding.get("resource_name", "unknown"),
                        agent_name=finding.get("agent_name", "unknown"),
                        explanation=enriched,
                        event_id=str(event_id),
                        pr_url=pr.pr_url,
                    )
                    log.info("[workflow] %s REMEDIATED → %s", check_id, pr.pr_url)
                    return LoopOutcome(status="REMEDIATED", pr_url=pr.pr_url)
                else:
                    await escalate_event(session, event_id, violation_description=enriched)
                    await post_escalation(
                        check_id=check_id,
                        control_id=control_id,
                        control_name=control_name,
                        severity=finding.get("severity", "MEDIUM"),
                        resource_name=finding.get("resource_name", "unknown"),
                        agent_name=finding.get("agent_name", "unknown"),
                        explanation=enriched,
                        event_id=str(event_id),
                        detail="post-patch scan still failing",
                    )
                    log.warning("[workflow] %s validation FAILED → escalated", check_id)
                    return LoopOutcome(
                        status="ESCALATED",
                        pr_url=pr.pr_url,
                        detail="post-patch scan still failing",
                    )

        except Exception as exc:
            log.error("[workflow] crashed for %s: %s", check_id, exc)
            return LoopOutcome(status="ERROR", detail=str(exc))
