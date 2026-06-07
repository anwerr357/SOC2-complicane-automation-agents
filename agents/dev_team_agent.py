"""
agents/dev_team_agent.py
────────────────────────
Dev Team Agent — watches GitHub pull requests and code pushes.

Subscribes to: github.prs
Controls: CC6.1, CC6.3, CC7.2, CC8.1

Week 5: on each event the agent
  1. logs a CC8.1 change-management event (unchanged from Week 4),
  2. shallow-clones the repo at the pushed sha into a temp dir,
  3. runs Trufflehog (secrets) and Semgrep (custom rules) over it,
  4. feeds every finding through the shared run_remediation_loop().
"""
from __future__ import annotations

import asyncio
import logging
import os
import stat
import tempfile

from agents.base_agent import BaseAgent
from agents.remediation import run_remediation_loop
from brain.rag import retrieve_by_control_id
from scanners.semgrep_runner import SemgrepRunner
from scanners.trufflehog_runner import TrufflehogRunner
from store.evidence import get_session, log_event

log = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
CLONE_DEPTH = int(os.environ.get("CLONE_DEPTH", "1"))


async def _shallow_clone(
    repo_full_name: str,
    sha: str,
    token: str,
    dest: str,
    *,
    depth: int = 1,
) -> str:
    """Shallow-clone repo into dest using token auth. Returns dest.

    Security: the token is NEVER placed on the command line (argv is readable
    via `ps` / /proc/<pid>/cmdline) nor embedded in the clone URL (git would
    persist that into the cloned repo's .git/config, leaving a live credential
    in the very tree the scanners then walk). Instead it is supplied to git
    through a short-lived, owner-only GIT_ASKPASS helper that reads the token
    from the child process environment and is deleted immediately after.
    """
    # URL carries only the non-secret username; the token is the "password"
    # provided by the askpass helper below.
    url = f"https://x-access-token@github.com/{repo_full_name}.git"

    askpass = tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", prefix="gh-askpass-", delete=False
    )
    try:
        # Helper echoes the token from the env — the secret is never written
        # into the script file itself (avoids any interpolation/injection).
        askpass.write('#!/bin/sh\nprintf "%s" "$GH_TOKEN"\n')
        askpass.close()
        os.chmod(askpass.name, stat.S_IRWXU)  # 0o700 — owner only

        env = {
            **os.environ,
            "GIT_ASKPASS": askpass.name,
            "GH_TOKEN": token,
            "GIT_TERMINAL_PROMPT": "0",
        }
        cmd = ["git", "clone", "--depth", str(depth), url, dest]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _, stderr_b = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"git clone failed for {repo_full_name}: "
                f"{stderr_b.decode(errors='replace')[:300]}"
            )
        return dest
    finally:
        try:
            os.unlink(askpass.name)
        except OSError:
            pass


class DevTeamAgent(BaseAgent):
    NAME = "dev_team"
    STREAMS = ["github.prs"]
    CONTROLS = ["CC6.1", "CC6.3", "CC7.2", "CC8.1"]

    async def handle_event(self, stream: str, event: dict) -> None:
        event_type = event.get("event_type", "unknown")
        repo = event.get("repo", "unknown")
        sha = event.get("sha", "")

        log.info(
            "[DevTeamAgent] GitHub event: type=%s repo=%s sha=%s",
            event_type, repo, sha,
        )

        # ── CC8.1 — log the push as a change-management event ──────────────
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

        if not GITHUB_TOKEN:
            log.warning("[DevTeamAgent] No GITHUB_TOKEN — skipping scan for %s.", repo)
            return

        # ── Clone + scan + remediate ───────────────────────────────────────
        with tempfile.TemporaryDirectory(prefix="devteam-") as tmp:
            try:
                await _shallow_clone(
                    repo, sha, GITHUB_TOKEN, tmp, depth=CLONE_DEPTH
                )
            except RuntimeError as exc:
                log.error("[DevTeamAgent] clone failed: %s", exc)
                return

            findings: list[dict] = []
            try:
                th = await TrufflehogRunner().scan(tmp, git_sha=sha)
                findings += [f.to_evidence_dict() for f in th]
            except Exception as exc:
                log.error("[DevTeamAgent] trufflehog failed: %s", exc)
            try:
                sg = await SemgrepRunner().scan(tmp, git_sha=sha)
                findings += [f.to_evidence_dict() for f in sg]
            except Exception as exc:
                log.error("[DevTeamAgent] semgrep failed: %s", exc)

            log.info("[DevTeamAgent] %d code findings for %s.", len(findings), repo)
            for finding in findings:
                outcome = await run_remediation_loop(
                    finding,
                    repo_full_name=repo,
                    github_token=GITHUB_TOKEN,
                )
                log.info(
                    "[DevTeamAgent] %s → %s",
                    finding.get("check_id"), outcome.status,
                )
