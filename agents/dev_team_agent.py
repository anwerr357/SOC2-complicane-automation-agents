"""
agents/dev_team_agent.py
────────────────────────
Dev Team Agent — watches GitHub pull requests and code pushes.

Subscribes to
─────────────
github.prs  — GitHub push and pull_request events (published by webhooks.py)

Owns controls
─────────────
CC6.1  Logical and physical access controls  (secrets in code)
CC6.3  Access removal                        (offboarding)
CC7.2  Audit logging and monitoring          (missing audit_log() calls)
CC8.1  Change management                     (unreviewed changes)

Scanners (Week 3 stubs — implemented in Week 5)
────────────────────────────────────────────────
Trufflehog — scans git history for live secrets (CC6.1, CC6.2)
Semgrep    — SAST with custom rules (CC7.2 — missing audit_log() calls)

Week 4 scope
────────────
Receives events from the github.prs Redis Stream.
Logs the event to the evidence store as CC8.1 (change management).
Full Trufflehog + Semgrep pipeline added in Week 5.
"""

from __future__ import annotations

import logging
import os

from agents.base_agent import BaseAgent
from brain.rag import retrieve_by_control_id
from store.evidence import get_session, log_event

log = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")


class DevTeamAgent(BaseAgent):
    """
    Watches GitHub pull requests and code pushes.

    Week 4: receives events and logs them as CC8.1 change-management events.
    Week 5: adds Trufflehog + Semgrep scanning per PR.
    """

    NAME     = "dev_team"
    STREAMS  = ["github.prs"]
    CONTROLS = ["CC6.1", "CC6.3", "CC7.2", "CC8.1"]

    async def handle_event(self, stream: str, event: dict) -> None:
        event_type = event.get("event_type", "unknown")
        repo       = event.get("repo",       "unknown")
        sha        = event.get("sha",        "")

        log.info(
            "[DevTeamAgent] GitHub event: type=%s repo=%s sha=%s",
            event_type, repo, sha,
        )

        # ── CC8.1 — log every push as a change management event ────────────
        control = await retrieve_by_control_id("CC8.1", QDRANT_URL)

        async with get_session() as session:
            await log_event(session, {
                "agent_name":   self.NAME,
                "scanner_used": "manual",
                "check_id":     f"GITHUB_{event_type.upper()}",
                "control_id":   "CC8.1",
                "control_name": control.control_name,
                "resource_name": repo,
                "file_path":    repo,
                "git_sha":      sha or None,
                "severity":     "INFO",
                "violation_description": (
                    f"GitHub {event_type} event received for {repo}. "
                    f"SHA: {sha}. "
                    f"Week 5: Trufflehog + Semgrep will scan this push."
                ),
                "raw_finding": {
                    "event_type": event_type,
                    "repo":       repo,
                    "sha":        sha,
                    "source":     "github_webhook",
                },
            })

        # TODO (Week 5): run Trufflehog on the branch
        # TODO (Week 5): run Semgrep with custom audit_log() rules
        log.info("[DevTeamAgent] CC8.1 event logged for %s/%s.", repo, event_type)
