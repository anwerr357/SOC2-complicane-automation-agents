"""
agents/remediation.py
─────────────────────
The shared 5-step remediation loop, written once and reused by every agent.

    1 NOTIFY    log the violation to the evidence store (status=OPEN)
    2 LEARN     fetch the SOC 2 control text from Qdrant (RAG)
    3 RECOMMEND ask Claude for a plain-English explanation
    4 MUTATE    open a remediation PR on GitHub
    5 VALIDATE  re-scan the patched content; mark REMEDIATED or ESCALATED

All external calls reuse existing modules. Each call is imported at module
scope so tests can monkeypatch them. The whole loop is wrapped so one bad
finding never crashes the calling agent.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from brain.llm import generate_explanation
from brain.rag import retrieve_by_control_id
from mutate.mutate import open_remediation_pr
from mutate.validate import validate_remediation
from store.evidence import (
    escalate_event,
    get_session,
    log_event,
    update_remediation,
)

log = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")

# Scanners whose findings can be re-scanned by validate_remediation; only these
# are eligible for auto-remediation (MUTATE + VALIDATE). K8s drift findings
# (scanner_used="k8s_watch") fall outside this set and are escalated instead.
_VALIDATE_SUPPORTED = {"checkov", "semgrep", "trufflehog"}


@dataclass
class LoopOutcome:
    status: str            # REMEDIATED | ESCALATED | ERROR
    pr_url: str | None = None
    detail: str = ""


async def run_remediation_loop(
    finding: dict,
    *,
    repo_full_name: str,
    github_token: str,
) -> LoopOutcome:
    """Run steps 1–5 for a single finding. Never raises."""
    check_id = finding.get("check_id", "?")
    control_id = finding.get("control_id", "CC0.0")
    try:
        # 1 NOTIFY ----------------------------------------------------------
        async with get_session() as session:
            event = await log_event(session, finding)
            await session.commit()
            event_id = event.id

        # 2 LEARN -----------------------------------------------------------
        control = await retrieve_by_control_id(control_id, QDRANT_URL)

        # 3 RECOMMEND -------------------------------------------------------
        explanation = await generate_explanation(
            check_id=check_id,
            control_id=control_id,
            control_name=finding.get("control_name", control.control_name),
            control_text=control.text,
            resource_name=finding.get("resource_name", "unknown"),
            file_path=finding.get("file_path", "unknown"),
            severity=finding.get("severity", "MEDIUM"),
        )
        enriched = (
            f"{explanation.violation_summary}\n\n"
            f"{explanation.business_impact}\n\n"
            f"Remediation: {explanation.remediation_steps}"
        )

        # Decide whether this finding can be auto-fixed by a PR -------------
        patch_path = finding.get("repo_file_path") or finding.get("file_path")
        remediable = bool(
            repo_full_name
            and github_token
            and patch_path
            and finding.get("scanner_used") in _VALIDATE_SUPPORTED
        )

        if not remediable:
            async with get_session() as session:
                await escalate_event(
                    session, event_id, violation_description=enriched
                )
                await session.commit()
            log.warning("[loop] %s not auto-remediable → escalated", check_id)
            return LoopOutcome(
                status="ESCALATED",
                detail="not auto-remediable — human review",
            )

        # 4 MUTATE ----------------------------------------------------------
        pr = await open_remediation_pr(
            github_token=github_token,
            repo_full_name=repo_full_name,
            file_path=patch_path,
            check_id=check_id,
            control_id=control_id,
            control_name=finding.get("control_name", control.control_name),
            resource_name=finding.get("resource_name", "unknown"),
            severity=finding.get("severity", "MEDIUM"),
            violation_description=explanation.violation_summary,
            control_text=control.text,
        )

        # 5 VALIDATE --------------------------------------------------------
        ok = await validate_remediation(finding, pr.patched_content)
        async with get_session() as session:
            if ok:
                await update_remediation(
                    session, event_id, pr_url=pr.pr_url, pr_number=pr.pr_number,
                    violation_description=enriched,
                )
                await session.commit()
                log.info("[loop] %s REMEDIATED → %s", check_id, pr.pr_url)
                return LoopOutcome(status="REMEDIATED", pr_url=pr.pr_url)
            else:
                await escalate_event(
                    session, event_id, violation_description=enriched
                )
                await session.commit()
                log.warning("[loop] %s validation FAILED → escalated", check_id)
                return LoopOutcome(
                    status="ESCALATED", pr_url=pr.pr_url,
                    detail="post-patch scan still failing",
                )

    except Exception as exc:
        log.error("[loop] remediation loop crashed for %s: %s", check_id, exc)
        return LoopOutcome(status="ERROR", detail=str(exc))
