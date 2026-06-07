"""Integration tests for the Trufflehog runner. Requires the `trufflehog` CLI."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scanners.trufflehog_runner import TrufflehogRunner, run_trufflehog

SECRET_REPO = Path(__file__).parent / "fixtures" / "secret_repo"

requires_trufflehog = pytest.mark.skipif(
    shutil.which("trufflehog") is None, reason="trufflehog CLI not installed"
)


@pytest.fixture
def runner() -> TrufflehogRunner:
    return TrufflehogRunner()


@requires_trufflehog
@pytest.mark.asyncio
async def test_scan_finds_planted_secret(runner: TrufflehogRunner):
    findings = await runner.scan(SECRET_REPO, git_sha="test-sha")
    assert findings, "Expected trufflehog to find the planted AWS secret"
    assert any("AWS" in f.detector_name.upper() for f in findings)


@requires_trufflehog
@pytest.mark.asyncio
async def test_findings_map_to_access_controls(runner: TrufflehogRunner):
    findings = await runner.scan(SECRET_REPO)
    assert all(f.control_id in {"CC6.1", "CC6.2"} for f in findings)


@requires_trufflehog
@pytest.mark.asyncio
async def test_to_evidence_dict_shape(runner: TrufflehogRunner):
    findings = await runner.scan(SECRET_REPO)
    required = {
        "agent_name", "scanner_used", "check_id", "control_id",
        "control_name", "resource_name", "file_path", "severity", "raw_finding",
    }
    for f in findings:
        assert not (required - f.to_evidence_dict().keys())
        assert f.to_evidence_dict()["scanner_used"] == "trufflehog"


@requires_trufflehog
@pytest.mark.asyncio
async def test_convenience_function():
    assert isinstance(await run_trufflehog(SECRET_REPO), list)


@pytest.mark.asyncio
async def test_missing_binary_raises():
    runner = TrufflehogRunner(binary="trufflehog_does_not_exist_xyz")
    with pytest.raises(RuntimeError):
        await runner.scan(SECRET_REPO)
