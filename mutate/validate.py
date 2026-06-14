"""Post-remediation validator (step 5): re-scan patched content to confirm the original check no longer fires."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Fallback extension per scanner when the finding's file_path has none.
_DEFAULT_EXT = {"checkov": ".tf", "semgrep": ".py"}


def _ext_for(finding: dict, scanner: str) -> str:
    suffix = Path(finding.get("file_path", "")).suffix
    return suffix or _DEFAULT_EXT.get(scanner, ".txt")


async def validate_remediation(finding: dict, patched_content: str) -> bool:
    """Re-verify that the violation described by `finding` is gone after patching."""
    scanner = (finding.get("scanner_used") or "").lower()
    check_id = finding.get("check_id", "")

    try:
        if scanner == "trufflehog":
            # A single-file re-scan can't redo history analysis, so confirm the
            # raw secret string is absent from the patched content.
            secret = (finding.get("raw_finding") or {}).get("Raw", "")
            if not secret:
                log.warning("Trufflehog finding has no Raw secret; cannot validate.")
                return False
            return secret not in patched_content

        if scanner in ("checkov", "semgrep"):
            with tempfile.TemporaryDirectory() as d:
                fpath = Path(d) / f"patched{_ext_for(finding, scanner)}"
                fpath.write_text(patched_content)
                if scanner == "checkov":
                    from scanners.checkov_runner import run_checkov
                    results = await run_checkov(fpath)
                else:
                    from scanners.semgrep_runner import run_semgrep
                    results = await run_semgrep(fpath)
                still_failing = {r.check_id for r in results}
                return check_id not in still_failing

        log.warning("validate_remediation: unknown scanner '%s'", scanner)
        return False

    except Exception as exc:
        log.error("validate_remediation failed for %s: %s", check_id, exc)
        return False
