"""
scanners/trufflehog_runner.py
──────────────────────────────
Async subprocess wrapper around the Trufflehog secret scanner.

Mirrors the CheckovRunner contract: scan(path) -> list[TrufflehogFinding],
each finding carries a normalised SOC 2 mapping and a to_evidence_dict().

Trufflehog scans git history and emits one JSON object per line (JSONL).
We map verified (live) secrets to CC6.1 / HIGH and unverified to CC6.2 / MEDIUM.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_VERIFIED_CONTROL = ("CC6.1", "Logical and physical access controls")
_UNVERIFIED_CONTROL = ("CC6.2", "Authentication and multi-factor authentication")


@dataclass
class TrufflehogFinding:
    detector_name: str
    file_path: str
    line: int
    verified: bool
    severity: str
    control_id: str
    control_name: str
    check_id: str
    git_sha: str | None = None
    raw_finding: dict = field(default_factory=dict)

    def to_evidence_dict(self) -> dict:
        return {
            "agent_name": "dev_team",
            "scanner_used": "trufflehog",
            "check_id": self.check_id,
            "control_id": self.control_id,
            "control_name": self.control_name,
            "resource_name": self.detector_name,
            "file_path": self.file_path,
            "git_sha": self.git_sha,
            "severity": self.severity,
            "violation_description": "",
            "raw_finding": self.raw_finding,
        }


class TrufflehogRunner:
    def __init__(self, binary: str = "trufflehog") -> None:
        self._bin = binary

    async def _find_binary(self) -> str:
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, shutil.which, self._bin)
        if path is None:
            raise RuntimeError(
                f"'{self._bin}' not found on PATH. Install: "
                "https://github.com/trufflesecurity/trufflehog"
            )
        return path

    async def scan(
        self,
        repo_path: str | Path,
        *,
        git_sha: str | None = None,
        timeout: int = 180,
    ) -> list[TrufflehogFinding]:
        binary = await self._find_binary()
        repo_path = str(Path(repo_path).resolve())
        cmd = [binary, "git", f"file://{repo_path}", "--json", "--no-update"]
        log.info("Running Trufflehog: %s", " ".join(cmd))

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
                f"Trufflehog timed out after {timeout}s on {repo_path}"
            )

        # Trufflehog exits non-zero when secrets are found; that is not an error.
        findings: list[TrufflehogFinding] = []
        for raw_line in stdout_b.decode(errors="replace").splitlines():
            line = raw_line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            finding = self._normalise(obj, git_sha=git_sha)
            if finding:
                findings.append(finding)

        log.info("Trufflehog: %d secret findings in %s", len(findings), repo_path)
        return findings

    def _normalise(self, obj: dict, *, git_sha: str | None) -> TrufflehogFinding | None:
        # Only result objects carry DetectorName; skip log/info lines.
        detector = obj.get("DetectorName")
        if not detector:
            return None
        verified = bool(obj.get("Verified", False))
        control_id, control_name = (
            _VERIFIED_CONTROL if verified else _UNVERIFIED_CONTROL
        )
        severity = "HIGH" if verified else "MEDIUM"
        git_meta = (
            obj.get("SourceMetadata", {}).get("Data", {}).get("Git", {})
        )
        file_path = git_meta.get("file", "unknown")
        line = int(git_meta.get("line", 0) or 0)
        return TrufflehogFinding(
            detector_name=str(detector),
            file_path=file_path,
            line=line,
            verified=verified,
            severity=severity,
            control_id=control_id,
            control_name=control_name,
            check_id=f"TRUFFLEHOG_{str(detector).upper()}",
            git_sha=git_sha,
            raw_finding=obj,
        )


async def run_trufflehog(
    repo_path: str | Path, *, git_sha: str | None = None, timeout: int = 180
) -> list[TrufflehogFinding]:
    return await TrufflehogRunner().scan(repo_path, git_sha=git_sha, timeout=timeout)
