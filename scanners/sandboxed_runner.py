"""Runs Semgrep, Trufflehog, and Checkov inside ephemeral Daytona sandboxes."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from daytona import AsyncDaytona, CreateSandboxFromSnapshotParams

from scanners.checkov_runner import CheckovFinding, CheckovRunner
from scanners.semgrep_runner import SemgrepFinding, SemgrepRunner
from scanners.trufflehog_runner import TrufflehogFinding, TrufflehogRunner

log = logging.getLogger(__name__)

_RULES_DIR = Path(__file__).parents[1] / "semgrep_rules"

# Only allow well-formed GitHub HTTPS URLs — no shell metacharacters.
_GITHUB_URL_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9][A-Za-z0-9_.\-]*/[A-Za-z0-9][A-Za-z0-9_.\-]*$"
)
# Only allow relative paths with safe characters — no traversal, no leading dash.
_FILE_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-/]*$")


def _validate_repo_url(url: str) -> None:
    """Raise ValueError if url is not a safe GitHub HTTPS URL."""
    if not _GITHUB_URL_RE.match(url):
        raise ValueError(f"Unsafe or unsupported repo URL: {url!r}")


def _validate_file_path(path: str) -> None:
    """Raise ValueError if path contains unsafe characters or path traversal."""
    if not _FILE_PATH_RE.match(path):
        raise ValueError(f"Unsafe file path: {path!r}")
    if ".." in path.split("/"):
        raise ValueError(f"Path traversal not allowed: {path!r}")


@dataclass
class ScanResult:
    semgrep: list[SemgrepFinding] = field(default_factory=list)
    trufflehog: list[TrufflehogFinding] = field(default_factory=list)
    checkov: list[CheckovFinding] = field(default_factory=list)

    def all_findings(self) -> list[dict]:
        """Return all findings as evidence dicts, ordered: trufflehog → semgrep → checkov."""
        return (
            [f.to_evidence_dict() for f in self.trufflehog]
            + [f.to_evidence_dict() for f in self.semgrep]
            + [f.to_evidence_dict() for f in self.checkov]
        )


def _normalize_paths(result: ScanResult) -> None:
    """Strip /workspace/ prefix from all file_path fields."""
    for f in result.trufflehog + result.semgrep + result.checkov:
        if hasattr(f, "file_path"):
            f.file_path = _strip_workspace_prefix(f.file_path)


class SandboxedScanRunner:
    def __init__(
        self,
        snapshot: str | None = None,
        github_token: str | None = None,
    ) -> None:
        self._snapshot = snapshot or os.environ.get(
            "DAYTONA_SCANNER_SNAPSHOT", "compliance-scanner-v1"
        )
        self._github_token = github_token if github_token is not None else os.environ.get(
            "GITHUB_TOKEN", ""
        )

    async def scan(
        self,
        repo_url: str,
        *,
        git_sha: str | None = None,
    ) -> ScanResult:
        """Clone repo in sandbox, run all three tools, return combined findings."""
        async with AsyncDaytona() as daytona:
            sandbox = await daytona.create(
                CreateSandboxFromSnapshotParams(
                    snapshot=self._snapshot,
                    env_vars={"GITHUB_TOKEN": self._github_token},
                )
            )
            try:
                await self._clone(sandbox, repo_url)
                await self._upload_semgrep_rules(sandbox)
                return await self._run_all_tools(sandbox, git_sha=git_sha)
            finally:
                try:
                    await sandbox.delete()
                except Exception as exc:
                    log.warning("sandbox delete failed: %s", exc)

    async def _clone(self, sandbox, repo_url: str) -> None:
        _validate_repo_url(repo_url)
        # Use ${GITHUB_TOKEN} shell variable — token is already in sandbox env via
        # env_vars at create time, so it never appears in this Python string.
        clone_url = repo_url.replace("https://", "https://x-access-token:${GITHUB_TOKEN}@", 1)
        resp = await sandbox.process.exec(f"git clone {clone_url} /workspace")
        if resp.exit_code != 0:
            raise RuntimeError(f"git clone failed (exit {resp.exit_code}): {resp.result[:300]}")

    async def _upload_semgrep_rules(self, sandbox) -> None:
        for rule_file in _RULES_DIR.rglob("*"):
            if rule_file.is_file():
                rel = rule_file.relative_to(_RULES_DIR)
                await sandbox.fs.upload_file(
                    rule_file.read_bytes(), f"/rules/{rel}"
                )

    async def scan_file(
        self,
        repo_url: str,
        repo_file_path: str,
        *,
        git_sha: str | None = None,
    ) -> ScanResult:
        """Clone repo in sandbox, run Checkov on a single file, return findings."""
        async with AsyncDaytona() as daytona:
            sandbox = await daytona.create(
                CreateSandboxFromSnapshotParams(
                    snapshot=self._snapshot,
                    env_vars={"GITHUB_TOKEN": self._github_token},
                )
            )
            try:
                await self._clone(sandbox, repo_url)
                _validate_file_path(repo_file_path)
                result = ScanResult()
                try:
                    resp = await sandbox.process.exec(
                        f"checkov -f /workspace/{repo_file_path} "
                        f"--output json --quiet --compact"
                    )
                    if resp.exit_code not in (0, 1):
                        log.warning(
                            "checkov exited %d on %s — no findings collected",
                            resp.exit_code,
                            repo_file_path,
                        )
                    else:
                        result.checkov = _parse_checkov_output(
                            resp.result, git_sha=git_sha
                        )
                except Exception as exc:
                    log.warning("checkov scan_file failed in sandbox: %s", exc)
                _normalize_paths(result)
                return result
            finally:
                try:
                    await sandbox.delete()
                except Exception as exc:
                    log.warning("sandbox delete failed: %s", exc)

    async def _run_all_tools(self, sandbox, *, git_sha: str | None) -> ScanResult:
        result = ScanResult()

        # Trufflehog — exits non-zero when secrets found; that is valid output
        try:
            resp = await sandbox.process.exec(
                "trufflehog git file:///workspace --json --no-update"
            )
            result.trufflehog = _parse_trufflehog_output(resp.result, git_sha=git_sha)
            if resp.exit_code > 1:
                log.warning("trufflehog exited %d — possible crash", resp.exit_code)
                result.trufflehog = []
        except Exception as exc:
            log.warning("trufflehog failed in sandbox: %s", exc)

        # Semgrep — exits 0 (no findings) or 1 (findings found)
        try:
            resp = await sandbox.process.exec(
                "semgrep --config /rules --json --quiet --no-git-ignore /workspace"
            )
            if resp.exit_code not in (0, 1):
                log.warning("semgrep exited %d — no findings collected", resp.exit_code)
            else:
                result.semgrep = _parse_semgrep_output(resp.result, git_sha=git_sha)
        except Exception as exc:
            log.warning("semgrep failed in sandbox: %s", exc)

        # Checkov — exits 0 (all passed) or 1 (some failed)
        try:
            resp = await sandbox.process.exec(
                "checkov -d /workspace --output json --quiet --compact"
            )
            if resp.exit_code not in (0, 1):
                log.warning("checkov exited %d — no findings collected", resp.exit_code)
            else:
                result.checkov = _parse_checkov_output(resp.result, git_sha=git_sha)
        except Exception as exc:
            log.warning("checkov failed in sandbox: %s", exc)

        _normalize_paths(result)
        return result


# ---------------------------------------------------------------------------
# Pure parse helpers — call existing runner normalisation logic
# ---------------------------------------------------------------------------

_semgrep_runner = SemgrepRunner()
_trufflehog_runner = TrufflehogRunner()
_checkov_runner = CheckovRunner()


def _inject_token(repo_url: str, token: str) -> str:
    """Insert GitHub token credentials into an https:// URL."""
    if not token or not repo_url.startswith("https://"):
        return repo_url
    return repo_url.replace("https://", f"https://x-access-token:{token}@", 1)


def _strip_workspace_prefix(path: str, workspace: str = "/workspace") -> str:
    """Convert /workspace/src/main.py → src/main.py."""
    prefix = workspace + "/"
    return path[len(prefix):] if path.startswith(prefix) else path


def _parse_trufflehog_output(
    output: str, *, git_sha: str | None
) -> list[TrufflehogFinding]:
    findings: list[TrufflehogFinding] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        f = _trufflehog_runner._normalise(obj, git_sha=git_sha)
        if f:
            findings.append(f)
    return findings


def _parse_semgrep_output(
    output: str, *, git_sha: str | None
) -> list[SemgrepFinding]:
    text = output.strip()
    if not text:
        return []
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Failed to parse Semgrep JSON from sandbox output")
        return []
    findings = [
        _semgrep_runner._normalise(r, git_sha=git_sha)
        for r in raw.get("results", [])
    ]
    return [f for f in findings if f]


def _parse_checkov_output(
    output: str, *, git_sha: str | None
) -> list[CheckovFinding]:
    text = output.strip()
    if not text:
        return []
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Failed to parse Checkov JSON from sandbox output")
        return []
    return _checkov_runner._parse_results(raw, file_path="sandbox", git_sha=git_sha)
