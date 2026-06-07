"""Integration tests for the Semgrep runner. Requires the `semgrep` CLI."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scanners.semgrep_runner import SemgrepRunner, run_semgrep

SAMPLES = Path(__file__).parent / "fixtures" / "semgrep_samples"
RULES = Path(__file__).parents[1] / "semgrep_rules"

requires_semgrep = pytest.mark.skipif(
    shutil.which("semgrep") is None, reason="semgrep CLI not installed"
)


@pytest.fixture
def runner() -> SemgrepRunner:
    return SemgrepRunner(rules_dir=RULES)


@requires_semgrep
@pytest.mark.asyncio
async def test_detects_all_three_rules(runner: SemgrepRunner):
    findings = await runner.scan(SAMPLES)
    rule_ids = {f.rule_id for f in findings}
    assert "db-write-without-audit-log" in rule_ids
    assert "hardcoded-secret-assignment" in rule_ids
    assert "dangerous-dynamic-execution" in rule_ids


@requires_semgrep
@pytest.mark.asyncio
async def test_control_mapping_from_metadata(runner: SemgrepRunner):
    findings = await runner.scan(SAMPLES)
    by_rule = {f.rule_id: f for f in findings}
    assert by_rule["db-write-without-audit-log"].control_id == "CC7.2"
    assert by_rule["hardcoded-secret-assignment"].control_id == "CC6.1"


@requires_semgrep
@pytest.mark.asyncio
async def test_to_evidence_dict_shape(runner: SemgrepRunner):
    findings = await runner.scan(SAMPLES)
    required = {
        "agent_name", "scanner_used", "check_id", "control_id",
        "control_name", "resource_name", "file_path", "severity", "raw_finding",
    }
    for f in findings:
        d = f.to_evidence_dict()
        assert not (required - d.keys())
        assert d["scanner_used"] == "semgrep"


@requires_semgrep
@pytest.mark.asyncio
async def test_convenience_function():
    assert isinstance(await run_semgrep(SAMPLES, rules_dir=RULES), list)


@pytest.mark.asyncio
async def test_missing_binary_raises():
    runner = SemgrepRunner(binary="semgrep_does_not_exist_xyz", rules_dir=RULES)
    with pytest.raises(RuntimeError):
        await runner.scan(SAMPLES)
