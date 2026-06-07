"""
scanners/semgrep_runner.py
──────────────────────────
Async subprocess wrapper around Semgrep. Mirrors the CheckovRunner contract.

SOC 2 control mapping is read from each rule's YAML metadata
(extra.metadata.soc2_control / soc2_control_name / severity), so adding a
rule requires no Python change.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_RULES = Path(__file__).parents[1] / "semgrep_rules"
_UNKNOWN = ("CC0.0", "Unknown control — review manually")


@dataclass
class SemgrepFinding:
    rule_id: str
    file_path: str
    line: int
    message: str
    severity: str
    control_id: str
    control_name: str
    check_id: str
    git_sha: str | None = None
    raw_finding: dict = field(default_factory=dict)

    def to_evidence_dict(self) -> dict:
        return {
            "agent_name": "dev_team",
            "scanner_used": "semgrep",
            "check_id": self.check_id,
            "control_id": self.control_id,
            "control_name": self.control_name,
            "resource_name": self.rule_id,
            "file_path": self.file_path,
            "git_sha": self.git_sha,
            "severity": self.severity,
            "violation_description": self.message,
            "raw_finding": self.raw_finding,
        }


class SemgrepRunner:
    def __init__(
        self, binary: str = "semgrep", rules_dir: str | Path = _DEFAULT_RULES
    ) -> None:
        self._bin = binary
        self._rules_dir = str(Path(rules_dir).resolve())

    async def _find_binary(self) -> str:
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, shutil.which, self._bin)
        if path is None:
            raise RuntimeError(
                f"'{self._bin}' not found on PATH. Install: pip install semgrep"
            )
        return path

    async def scan(
        self,
        target: str | Path,
        *,
        git_sha: str | None = None,
        timeout: int = 180,
    ) -> list[SemgrepFinding]:
        binary = await self._find_binary()
        target = str(Path(target).resolve())
        cmd = [
            binary, "--config", self._rules_dir,
            "--json", "--quiet", "--no-git-ignore", target,
        ]
        log.info("Running Semgrep: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise asyncio.TimeoutError(
                f"Semgrep timed out after {timeout}s on {target}"
            )

        # Semgrep exits 0 (no findings) or 1 (findings). Anything else is a crash.
        if proc.returncode not in (0, 1):
            raise RuntimeError(
                f"Semgrep exited {proc.returncode}: "
                f"{stderr_b.decode(errors='replace')[:500]}"
            )

        text = stdout_b.decode(errors="replace").strip()
        if not text:
            return []
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            log.error("Failed to parse Semgrep JSON: %s", exc)
            return []

        findings = [
            self._normalise(r, git_sha=git_sha) for r in raw.get("results", [])
        ]
        findings = [f for f in findings if f]
        log.info("Semgrep: %d findings in %s", len(findings), target)
        return findings

    def _normalise(self, result: dict, *, git_sha: str | None) -> SemgrepFinding | None:
        try:
            rule_id = result.get("check_id", "unknown")
            # Semgrep prefixes rule ids with the rules dir path; keep the leaf.
            short_id = rule_id.split(".")[-1]
            extra = result.get("extra", {})
            meta = extra.get("metadata", {})
            control_id = meta.get("soc2_control") or _UNKNOWN[0]
            control_name = meta.get("soc2_control_name") or _UNKNOWN[1]
            severity = str(meta.get("severity", "MEDIUM")).upper()
            return SemgrepFinding(
                rule_id=short_id,
                file_path=result.get("path", "unknown"),
                line=int(result.get("start", {}).get("line", 0) or 0),
                message=extra.get("message", "").strip(),
                severity=severity,
                control_id=control_id,
                control_name=control_name,
                check_id=short_id,
                git_sha=git_sha,
                raw_finding=result,
            )
        except Exception as exc:
            log.warning("Could not normalise semgrep result: %s", exc)
            return None


async def run_semgrep(
    target: str | Path,
    *,
    rules_dir: str | Path = _DEFAULT_RULES,
    git_sha: str | None = None,
    timeout: int = 180,
) -> list[SemgrepFinding]:
    return await SemgrepRunner(rules_dir=rules_dir).scan(
        target, git_sha=git_sha, timeout=timeout
    )
