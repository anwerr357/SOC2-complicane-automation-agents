"""tests/test_checkov_runner.py"""

from __future__ import annotations

import pytest
from pathlib import Path

from scanners.checkov_runner import CheckovRunner, run_checkov


DEMO_TF = Path(__file__).parent / "fixtures" / "demo.tf"


@pytest.fixture
def runner() -> CheckovRunner:
    return CheckovRunner()


@pytest.mark.asyncio
async def test_scan_returns_findings(runner: CheckovRunner):
    """Scanning the demo fixture should return at least one violation."""
    findings = await runner.scan(DEMO_TF, git_sha="test-sha-001")
    assert len(findings) > 0, "Expected violations in demo.tf but got none"


@pytest.mark.asyncio
async def test_s3_encryption_violation(runner: CheckovRunner):
    """An S3 encryption violation must be detected and mapped to CC6.7."""
    findings = await runner.scan(DEMO_TF)
    cc67_findings = [f for f in findings if f.control_id == "CC6.7"]
    assert cc67_findings, (
        "Expected at least one CC6.7 (encryption at rest) violation in demo.tf.\n"
        f"Found check IDs: {sorted(f.check_id for f in findings)}"
    )
    # Also verify the s3 resource is named in at least one finding
    resource_names = {f.resource_name for f in cc67_findings}
    assert any("app_data" in r or "s3" in r.lower() or "bucket" in r.lower()
               for r in resource_names), (
        f"Expected an S3 bucket resource in CC6.7 findings, got: {resource_names}"
    )


@pytest.mark.asyncio
async def test_iam_wildcard_violation(runner: CheckovRunner):
    """IAM wildcard / overprivileged policy must be detected."""
    findings = await runner.scan(DEMO_TF)
    # IAM violations map to CC6.1 (logical access) or CC6.6 (least privilege)
    iam_controls = {"CC6.1", "CC6.6"}
    iam_findings = [f for f in findings if f.control_id in iam_controls]
    assert iam_findings, (
        f"Expected at least one CC6.1/CC6.6 (IAM) violation in demo.tf.\n"
        f"Found check IDs: {sorted(f.check_id for f in findings)}"
    )


@pytest.mark.asyncio
async def test_git_sha_attached(runner: CheckovRunner):
    """All findings should carry the git_sha passed to the runner."""
    sha = "deadbeef1234"
    findings = await runner.scan(DEMO_TF, git_sha=sha)
    for f in findings:
        assert f.git_sha == sha, f"Expected git_sha={sha} on finding {f.check_id}"


@pytest.mark.asyncio
async def test_to_evidence_dict_shape(runner: CheckovRunner):
    """to_evidence_dict() should return keys expected by log_event()."""
    findings = await runner.scan(DEMO_TF)
    required_keys = {
        "agent_name", "scanner_used", "check_id", "control_id",
        "control_name", "resource_name", "file_path", "severity",
        "raw_finding",
    }
    for f in findings:
        d = f.to_evidence_dict()
        missing = required_keys - d.keys()
        assert not missing, f"Finding {f.check_id} missing keys: {missing}"


@pytest.mark.asyncio
async def test_convenience_function():
    """Module-level run_checkov() function should work identically."""
    findings = await run_checkov(DEMO_TF)
    assert isinstance(findings, list)


@pytest.mark.asyncio
async def test_nonexistent_file():
    """Scanning a missing file should raise RuntimeError or return empty."""
    runner = CheckovRunner()
    # Checkov will exit with non-zero; we expect either an error or empty list
    try:
        findings = await runner.scan("/tmp/does_not_exist_12345.tf")
        # If it doesn't raise, it should be empty
        assert findings == []
    except (RuntimeError, FileNotFoundError):
        pass   # either outcome is acceptable
