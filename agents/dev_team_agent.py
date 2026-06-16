"""Dev Team Agent: scans pushed repos via Daytona sandboxed runner, feeds findings to the remediation loop."""

from __future__ import annotations

import logging
import os

from agents.base_agent import BaseAgent
from agents.remediation import run_remediation_loop
from brain.rag import retrieve_by_control_id
from scanners.sandboxed_runner import SandboxedScanRunner
from store.evidence import get_session, log_event

log = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")


class DevTeamAgent(BaseAgent):
    NAME = "dev_team"
    STREAMS = ["github.prs"]
    CONTROLS = ["CC6.1", "CC6.3", "CC7.2", "CC8.1"]

    async def handle_event(self, stream: str, event: dict) -> None:
        github_token = os.environ.get("GITHUB_TOKEN", "")
        event_type = event.get("event_type", "unknown")
        repo = event.get("repo", "unknown")
        sha = event.get("sha", "")

        log.info(
            "[DevTeamAgent] GitHub event: type=%s repo=%s sha=%s",
            event_type, repo, sha,
        )

        control = await retrieve_by_control_id("CC8.1", QDRANT_URL)
        async with get_session() as session:
            await log_event(session, {
                "agent_name": self.NAME,
                "scanner_used": "manual",
                "check_id": f"GITHUB_{event_type.upper()}",
                "control_id": "CC8.1",
                "control_name": control.control_name,
                "resource_name": repo,
                "file_path": repo,
                "git_sha": sha or None,
                "severity": "INFO",
                "violation_description": (
                    f"GitHub {event_type} event for {repo} (sha {sha})."
                ),
                "raw_finding": {
                    "event_type": event_type, "repo": repo, "sha": sha,
                    "source": "github_webhook",
                },
            })
            await session.commit()

        if not github_token:
            log.warning("[DevTeamAgent] No GITHUB_TOKEN — skipping scan for %s.", repo)
            return

        repo_url = f"https://github.com/{repo}"
        try:
            result = await SandboxedScanRunner().scan(repo_url, git_sha=sha or None)
        except Exception as exc:
            log.error("[DevTeamAgent] sandboxed scan failed for %s: %s", repo, exc)
            return

        findings = result.all_findings()
        log.info("[DevTeamAgent] %d findings for %s.", len(findings), repo)

        for finding in findings:
            finding.setdefault("repo_file_path", finding.get("file_path"))
            outcome = await run_remediation_loop(
                finding,
                repo_full_name=repo,
                github_token=github_token,
            )
            log.info(
                "[DevTeamAgent] %s → %s",
                finding.get("check_id"), outcome.status,
            )
