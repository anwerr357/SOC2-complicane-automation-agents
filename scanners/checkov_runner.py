"""
scanners/checkov_runner.py
──────────────────────────
Async subprocess wrapper around the Checkov IaC scanner.

What this module does
─────────────────────
1. Accepts a file path (Terraform .tf or Kubernetes YAML) and an optional
   git SHA for evidence attribution.
2. Runs `checkov --file <path> --output json --quiet` as a subprocess,
   capturing stdout (structured JSON) and stderr (progress/logs).
3. Parses the JSON, normalises every failed check into a `CheckovFinding`
   dataclass with a consistent shape.
4. Maps Checkov check IDs to SOC 2 Trust Service Criteria using a curated
   lookup table.
5. Returns a list of `CheckovFinding` objects ready to be passed directly
   to `store.evidence.log_event()`.

Design choices
──────────────
• Subprocess, not the Python SDK — Checkov's Python API is internal and
  changes frequently between minor versions.  The CLI is the stable surface.
• --quiet suppresses the progress bar so only JSON appears on stdout.
• asyncio.create_subprocess_exec is used throughout — the caller never
  blocks the event loop.
• Unknown check IDs are gracefully mapped to "CC0.0 / Unknown Control" so
  the pipeline never crashes on a new Checkov rule.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


# ── SOC 2 control mapping ──────────────────────────────────────────────────
# Maps Checkov check IDs → (SOC 2 control ID, human-readable control name)
# Maintained here because Checkov does not natively tag its findings with
# Trust Service Criteria.
#
# Sources: AICPA SOC 2 2017 TSC + Checkov documentation.
# Extend this dict as you add infrastructure coverage.

SOC2_CONTROL_MAP: dict[str, tuple[str, str]] = {
    # ── CC6.1 — Logical and physical access controls ───────────────────────
    "CKV_AWS_42":  ("CC6.1", "Logical and physical access controls"),
    "CKV_AWS_40":  ("CC6.1", "Logical and physical access controls"),
    "CKV_AWS_1":   ("CC6.1", "Logical and physical access controls"),
    "CKV_AWS_62":  ("CC6.1", "Logical and physical access controls"),
    "CKV_GCP_4":   ("CC6.1", "Logical and physical access controls"),
    "CKV_K8S_36":  ("CC6.1", "Logical and physical access controls"),
    "CKV_K8S_155": ("CC6.1", "Logical and physical access controls"),

    # ── CC6.2 — Authentication & MFA ──────────────────────────────────────
    "CKV_AWS_9":   ("CC6.2", "Authentication and multi-factor authentication"),
    "CKV_AWS_75":  ("CC6.2", "Authentication and multi-factor authentication"),

    # ── CC6.3 — Access removal & offboarding ──────────────────────────────
    "CKV_AWS_77":  ("CC6.3", "Access removal and user lifecycle management"),

    # ── CC6.6 — Least privilege & IAM hardening ───────────────────────────
    "CKV_AWS_274": ("CC6.6", "Least privilege and logical access restriction"),
    "CKV_AWS_355": ("CC6.6", "Least privilege and logical access restriction"),
    "CKV_AWS_289": ("CC6.6", "Least privilege and logical access restriction"),
    "CKV_AWS_290": ("CC6.6", "Least privilege and logical access restriction"),
    "CKV2_AWS_56": ("CC6.6", "Least privilege and logical access restriction"),
    "CKV_K8S_30":  ("CC6.6", "Least privilege and logical access restriction"),
    "CKV_K8S_32":  ("CC6.6", "Least privilege and logical access restriction"),

    # ── CC6.7 — Encryption at rest ────────────────────────────────────────
    "CKV_AWS_19":   ("CC6.7", "Encryption at rest"),   # S3 bucket encryption (legacy)
    "CKV_AWS_145":  ("CC6.7", "Encryption at rest"),   # S3 KMS encryption
    "CKV2_AWS_6":   ("CC6.7", "Encryption at rest"),   # S3 bucket-level encryption (v2)
    "CKV2_AWS_60":  ("CC6.7", "Encryption at rest"),   # S3 SSE enabled (v3.x)
    "CKV2_AWS_61":  ("CC6.7", "Encryption at rest"),   # S3 SSE + KMS (v3.x)
    "CKV2_AWS_62":  ("CC6.7", "Encryption at rest"),   # S3 default encryption (v3.x)
    "CKV_AWS_86":   ("CC6.7", "Encryption at rest"),
    "CKV_AWS_119":  ("CC6.7", "Encryption at rest"),   # DynamoDB encryption
    "CKV_AWS_211":  ("CC6.7", "Encryption at rest"),   # RDS encryption
    "CKV_AWS_17":   ("CC6.7", "Encryption at rest"),   # RDS public access
    "CKV_AWS_189":  ("CC6.7", "Encryption at rest"),
    "CKV_AWS_7":    ("CC6.7", "Encryption at rest"),   # KMS key rotation
    "CKV_GCP_62":   ("CC6.7", "Encryption at rest"),
    "CKV_AZURE_3":  ("CC6.7", "Encryption at rest"),

    # ── CC6.8 — Unauthorized or malicious software ────────────────────────
    "CKV_K8S_37":  ("CC6.8", "Unauthorized or malicious software protection"),
    "CKV_K8S_38":  ("CC6.8", "Unauthorized or malicious software protection"),
    "CKV_K8S_74":  ("CC6.8", "Unauthorized or malicious software protection"),

    # ── CC7.1 — System monitoring & alerting ─────────────────────────────
    "CKV_AWS_52":  ("CC7.1", "System monitoring and alerting"),
    "CKV_AWS_18":  ("CC7.1", "System monitoring and alerting"),   # S3 access logging
    "CKV_AWS_150": ("CC7.1", "System monitoring and alerting"),
    "CKV_AWS_76":  ("CC7.1", "System monitoring and alerting"),
    "CKV_GCP_26":  ("CC7.1", "System monitoring and alerting"),
    "CKV_K8S_21":  ("CC7.1", "System monitoring and alerting"),

    # ── CC7.2 — Audit logging ─────────────────────────────────────────────
    "CKV_AWS_67":  ("CC7.2", "Audit logging and monitoring"),
    "CKV_AWS_36":  ("CC7.2", "Audit logging and monitoring"),   # CloudTrail log validation
    "CKV_AWS_35":  ("CC7.2", "Audit logging and monitoring"),   # CloudTrail encryption
    "CKV2_AWS_10": ("CC7.2", "Audit logging and monitoring"),
    "CKV_GCP_27":  ("CC7.2", "Audit logging and monitoring"),
    "CKV_K8S_91":  ("CC7.2", "Audit logging and monitoring"),

    # ── CC8.1 — Change management ─────────────────────────────────────────
    "CKV2_AWS_5":  ("CC8.1", "Change management and authorised changes"),
    "CKV2_GCP_6":  ("CC8.1", "Change management and authorised changes"),

    # ── CC9.1 — Risk assessment ───────────────────────────────────────────
    "CKV_AWS_24":  ("CC9.1", "Risk assessment and mitigation"),
    "CKV_AWS_25":  ("CC9.1", "Risk assessment and mitigation"),

    # ── A1.1 — Availability / redundancy ─────────────────────────────────
    "CKV_AWS_91":  ("A1.1", "Availability and redundancy"),
    "CKV_AWS_92":  ("A1.1", "Availability and redundancy"),
    "CKV_K8S_8":   ("A1.1", "Availability and redundancy"),   # liveness probe
    "CKV_K8S_9":   ("A1.1", "Availability and redundancy"),   # readiness probe
}

_UNKNOWN_CONTROL = ("CC0.0", "Unknown control — review manually")

# Checkov severity label → our normalised Severity enum value
SEVERITY_MAP: dict[str, str] = {
    "critical": "HIGH",
    "high":     "HIGH",
    "medium":   "MEDIUM",
    "low":      "LOW",
    "info":     "INFO",
    "unknown":  "INFO",
}


# ── Data model ─────────────────────────────────────────────────────────────

@dataclass
class CheckovFinding:
    """
    Normalised representation of a single Checkov failed check.

    This is the shape that `store.evidence.log_event()` expects under the
    `raw_finding` key (plus the top-level scalar fields).
    """

    # Scanner-native fields
    check_id: str
    check_type: str          # terraform | kubernetes | cloudformation …
    resource_name: str
    file_path: str
    severity: str            # HIGH | MEDIUM | LOW | INFO

    # SOC 2 mapping (derived)
    control_id: str
    control_name: str

    # Evidence attribution
    git_sha: str | None = None

    # Full scanner payload — stored verbatim in Postgres JSONB
    raw_finding: dict = field(default_factory=dict)

    def to_evidence_dict(self) -> dict:
        """Return a dict shaped for `store.evidence.log_event()`."""
        return {
            "agent_name":             "policy",
            "scanner_used":           "checkov",
            "check_id":               self.check_id,
            "control_id":             self.control_id,
            "control_name":           self.control_name,
            "resource_name":          self.resource_name,
            "file_path":              self.file_path,
            "git_sha":                self.git_sha,
            "severity":               self.severity,
            "violation_description":  "",   # filled by LLM in Week 3
            "raw_finding":            self.raw_finding,
        }


# ── Runner ─────────────────────────────────────────────────────────────────

class CheckovRunner:
    """
    Async wrapper around the `checkov` CLI.

    Usage::

        runner = CheckovRunner()
        findings = await runner.scan("/path/to/main.tf", git_sha="abc123")
        for f in findings:
            print(f.check_id, f.control_id, f.resource_name)
    """

    def __init__(self, checkov_binary: str = "checkov") -> None:
        self._bin = checkov_binary

    async def _find_binary(self) -> str:
        """Verify the binary exists; raise RuntimeError if not."""
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, shutil.which, self._bin)
        if path is None:
            raise RuntimeError(
                f"'{self._bin}' not found on PATH.  "
                "Install it with: pip install checkov"
            )
        return path

    async def scan(
        self,
        file_path: str | Path,
        *,
        git_sha: str | None = None,
        timeout: int = 120,
    ) -> list[CheckovFinding]:
        """
        Run Checkov against a single file and return normalised findings.

        Parameters
        ──────────
        file_path : path to a .tf or .yaml/.yml file
        git_sha   : optional HEAD SHA for audit attribution
        timeout   : subprocess timeout in seconds (default 120)

        Returns
        ───────
        List of `CheckovFinding` for every *failed* check.
        Passed checks are silently discarded — they are not violations.

        Raises
        ──────
        RuntimeError   if the checkov binary is not found
        asyncio.TimeoutError  if the scan exceeds `timeout` seconds
        """
        binary = await self._find_binary()
        file_path = str(Path(file_path).resolve())

        cmd = [
            binary,
            "--file",   file_path,
            "--output", "json",
            "--quiet",                # suppress progress bar
            "--compact",              # no source-code snippets in JSON
        ]

        log.info("Running Checkov: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise asyncio.TimeoutError(
                f"Checkov timed out after {timeout}s scanning {file_path}"
            )

        # Checkov exits 0 (all passed) or 1 (some failed) or 2 (error).
        # We treat 0 and 1 as valid JSON responses; anything else is a crash.
        if proc.returncode not in (0, 1):
            stderr_text = stderr_bytes.decode(errors="replace")
            raise RuntimeError(
                f"Checkov exited with code {proc.returncode}.\n"
                f"stderr: {stderr_text}"
            )

        stdout_text = stdout_bytes.decode(errors="replace").strip()
        if not stdout_text:
            log.warning("Checkov produced no output for %s", file_path)
            return []

        try:
            raw = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            log.error("Failed to parse Checkov JSON: %s", exc)
            log.debug("Raw stdout: %s", stdout_text[:2000])
            return []

        return self._parse_results(raw, file_path=file_path, git_sha=git_sha)

    # ── Internal parsers ────────────────────────────────────────────────────

    def _parse_results(
        self,
        raw: dict | list,
        *,
        file_path: str,
        git_sha: str | None,
    ) -> list[CheckovFinding]:
        """
        Handle two Checkov output shapes:

        Shape A — single check type
            {"results": {"failed_checks": [...]}, "check_type": "terraform"}

        Shape B — multiple check types (when scanning a mixed directory)
            [{"results": ..., "check_type": "terraform"}, ...]
        """
        if isinstance(raw, list):
            findings: list[CheckovFinding] = []
            for block in raw:
                findings.extend(
                    self._parse_block(block, file_path=file_path, git_sha=git_sha)
                )
            return findings

        return self._parse_block(raw, file_path=file_path, git_sha=git_sha)

    def _parse_block(
        self,
        block: dict,
        *,
        file_path: str,
        git_sha: str | None,
    ) -> list[CheckovFinding]:
        check_type: str = block.get("check_type", "unknown")
        results: dict = block.get("results", {})
        failed_checks: list[dict] = results.get("failed_checks", [])

        findings: list[CheckovFinding] = []
        for check in failed_checks:
            finding = self._normalise_check(
                check,
                check_type=check_type,
                file_path=file_path,
                git_sha=git_sha,
            )
            if finding:
                findings.append(finding)

        log.info(
            "Checkov (%s): %d failed checks in %s",
            check_type,
            len(findings),
            file_path,
        )
        return findings

    def _normalise_check(
        self,
        check: dict,
        *,
        check_type: str,
        file_path: str,
        git_sha: str | None,
    ) -> CheckovFinding | None:
        try:
            check_id: str = check.get("check_id", "UNKNOWN")
            resource: str = check.get("resource", "unknown_resource")

            # Resolve SOC 2 control
            control_id, control_name = SOC2_CONTROL_MAP.get(
                check_id, _UNKNOWN_CONTROL
            )

            # Normalise severity
            raw_severity = (
                check.get("severity") or
                check.get("check_result", {}).get("result", "INFO")
            )
            if isinstance(raw_severity, dict):
                raw_severity = "INFO"
            severity = SEVERITY_MAP.get(str(raw_severity).lower(), "INFO")

            # Use the actual scanned file path from the check payload when
            # available (more precise in directory scans)
            effective_path = check.get("file_path") or file_path

            return CheckovFinding(
                check_id=check_id,
                check_type=check_type,
                resource_name=resource,
                file_path=effective_path,
                severity=severity,
                control_id=control_id,
                control_name=control_name,
                git_sha=git_sha,
                raw_finding=check,
            )
        except Exception as exc:
            log.warning("Could not normalise check %s: %s", check.get("check_id"), exc)
            return None


# ── Convenience function ───────────────────────────────────────────────────

async def run_checkov(
    file_path: str | Path,
    *,
    git_sha: str | None = None,
    timeout: int = 120,
) -> list[CheckovFinding]:
    """
    Module-level shorthand for one-off scans.

    Example::

        from scanners.checkov_runner import run_checkov
        findings = await run_checkov("infra/main.tf", git_sha="deadbeef")
    """
    runner = CheckovRunner()
    return await runner.scan(file_path, git_sha=git_sha, timeout=timeout)
