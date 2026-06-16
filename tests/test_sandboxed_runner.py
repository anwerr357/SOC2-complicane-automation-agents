"""Tests for SandboxedScanRunner — all Daytona API calls are mocked."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scanners.sandboxed_runner import (
    ScanResult,
    SandboxedScanRunner,
    _validate_repo_url,
    _validate_file_path,
)
from scanners.semgrep_runner import SemgrepFinding
from scanners.trufflehog_runner import TrufflehogFinding
from scanners.checkov_runner import CheckovFinding


def _make_semgrep_finding() -> SemgrepFinding:
    return SemgrepFinding(
        rule_id="hardcoded-secret-assignment",
        file_path="config.py",
        line=5,
        message="Hardcoded secret found",
        severity="HIGH",
        control_id="CC6.1",
        control_name="Logical and physical access controls",
        check_id="hardcoded-secret-assignment",
        git_sha="abc123",
    )


def _make_trufflehog_finding() -> TrufflehogFinding:
    return TrufflehogFinding(
        detector_name="AWS",
        file_path="config.py",
        line=5,
        verified=True,
        severity="HIGH",
        control_id="CC6.1",
        control_name="Logical and physical access controls",
        check_id="TRUFFLEHOG_AWS",
        git_sha="abc123",
    )


def _make_checkov_finding() -> CheckovFinding:
    return CheckovFinding(
        check_id="CKV_AWS_145",
        check_type="terraform",
        resource_name="aws_s3_bucket.app",
        file_path="main.tf",
        severity="HIGH",
        control_id="CC6.7",
        control_name="Encryption at rest",
        git_sha="abc123",
    )


class TestScanResult:
    def test_empty_by_default(self):
        r = ScanResult()
        assert r.semgrep == []
        assert r.trufflehog == []
        assert r.checkov == []

    def test_all_findings_returns_evidence_dicts(self):
        r = ScanResult(
            semgrep=[_make_semgrep_finding()],
            trufflehog=[_make_trufflehog_finding()],
            checkov=[_make_checkov_finding()],
        )
        all_f = r.all_findings()
        assert len(all_f) == 3
        assert all(isinstance(f, dict) for f in all_f)
        scanners = {f["scanner_used"] for f in all_f}
        assert scanners == {"semgrep", "trufflehog", "checkov"}

    def test_all_findings_order_is_trufflehog_semgrep_checkov(self):
        r = ScanResult(
            semgrep=[_make_semgrep_finding()],
            trufflehog=[_make_trufflehog_finding()],
            checkov=[_make_checkov_finding()],
        )
        all_f = r.all_findings()
        assert all_f[0]["scanner_used"] == "trufflehog"
        assert all_f[1]["scanner_used"] == "semgrep"
        assert all_f[2]["scanner_used"] == "checkov"


# ---------------------------------------------------------------------------
# Parse helper tests — no Daytona mocking needed
# ---------------------------------------------------------------------------

_TRUFFLEHOG_LINE = json.dumps({
    "DetectorName": "AWS",
    "Verified": True,
    "SourceMetadata": {"Data": {"Git": {"file": "/workspace/config.py", "line": 5}}},
})

_SEMGREP_OUTPUT = json.dumps({
    "results": [{
        "check_id": "rules.hardcoded-secret-assignment",
        "path": "/workspace/config.py",
        "start": {"line": 5},
        "extra": {
            "message": "Hardcoded secret",
            "metadata": {
                "soc2_control": "CC6.1",
                "soc2_control_name": "Logical and physical access controls",
                "severity": "HIGH",
            },
        },
    }],
})

_CHECKOV_OUTPUT = json.dumps({
    "check_type": "terraform",
    "results": {
        "failed_checks": [{
            "check_id": "CKV_AWS_145",
            "resource": "aws_s3_bucket.app",
            "severity": "high",
            "file_path": "/workspace/main.tf",
        }]
    },
})


from scanners.sandboxed_runner import (  # noqa: E402
    _parse_trufflehog_output,
    _parse_semgrep_output,
    _parse_checkov_output,
    _inject_token,
    _strip_workspace_prefix,
)


class TestParseHelpers:
    def test_parse_trufflehog_returns_finding(self):
        findings = _parse_trufflehog_output(_TRUFFLEHOG_LINE, git_sha="abc")
        assert len(findings) == 1
        assert findings[0].detector_name == "AWS"
        assert findings[0].verified is True

    def test_parse_trufflehog_skips_non_json_lines(self):
        output = "time=2024 level=info msg=starting\n" + _TRUFFLEHOG_LINE
        findings = _parse_trufflehog_output(output, git_sha=None)
        assert len(findings) == 1

    def test_parse_trufflehog_empty_output(self):
        assert _parse_trufflehog_output("", git_sha=None) == []

    def test_parse_semgrep_returns_finding(self):
        findings = _parse_semgrep_output(_SEMGREP_OUTPUT, git_sha="abc")
        assert len(findings) == 1
        assert findings[0].control_id == "CC6.1"

    def test_parse_semgrep_empty_output(self):
        assert _parse_semgrep_output("", git_sha=None) == []

    def test_parse_semgrep_invalid_json(self):
        assert _parse_semgrep_output("not-json", git_sha=None) == []

    def test_parse_checkov_returns_finding(self):
        findings = _parse_checkov_output(_CHECKOV_OUTPUT, git_sha="abc")
        assert len(findings) == 1
        assert findings[0].check_id == "CKV_AWS_145"
        assert findings[0].control_id == "CC6.7"

    def test_parse_checkov_empty_output(self):
        assert _parse_checkov_output("", git_sha=None) == []

    def test_inject_token_inserts_credentials(self):
        url = _inject_token("https://github.com/org/repo", "mytoken")
        assert url == "https://x-access-token:mytoken@github.com/org/repo"

    def test_inject_token_no_op_when_empty(self):
        url = _inject_token("https://github.com/org/repo", "")
        assert url == "https://github.com/org/repo"

    def test_strip_workspace_prefix_removes_leading_slash(self):
        assert _strip_workspace_prefix("/workspace/src/main.py") == "src/main.py"

    def test_strip_workspace_prefix_no_op_on_relative(self):
        assert _strip_workspace_prefix("src/main.py") == "src/main.py"


# ---------------------------------------------------------------------------
# SandboxedScanRunner.scan() tests — Daytona fully mocked
# ---------------------------------------------------------------------------

def _make_mock_sandbox(
    clone_exit: int = 0,
    th_output: str = "",
    sg_output: str = '{"results": []}',
    ck_output: str = '{"check_type": "terraform", "results": {"failed_checks": []}}',
) -> MagicMock:
    """Build a mock AsyncSandbox with pre-configured exec side effects."""
    sandbox = AsyncMock()
    sandbox.fs.upload_file = AsyncMock(return_value=None)
    sandbox.delete = AsyncMock(return_value=None)
    sandbox.process.exec = AsyncMock(side_effect=[
        MagicMock(exit_code=clone_exit, result=""),    # git clone
        MagicMock(exit_code=0,          result=th_output),   # trufflehog
        MagicMock(exit_code=0,          result=sg_output),   # semgrep
        MagicMock(exit_code=0,          result=ck_output),   # checkov
    ])
    return sandbox


def _patch_daytona(mock_sandbox: MagicMock):
    """Return a context manager that patches AsyncDaytona to return mock_sandbox."""
    mock_daytona = AsyncMock()
    mock_daytona.create = AsyncMock(return_value=mock_sandbox)
    mock_daytona.__aenter__ = AsyncMock(return_value=mock_daytona)
    mock_daytona.__aexit__ = AsyncMock(return_value=False)
    return patch("scanners.sandboxed_runner.AsyncDaytona", return_value=mock_daytona)


class TestSandboxedScanRunnerScan:
    @pytest.mark.asyncio
    async def test_scan_returns_scan_result(self):
        sandbox = _make_mock_sandbox(th_output=_TRUFFLEHOG_LINE)
        with _patch_daytona(sandbox):
            runner = SandboxedScanRunner(snapshot="test-snap", github_token="tok")
            result = await runner.scan("https://github.com/org/repo", git_sha="abc")
        assert isinstance(result, ScanResult)
        assert len(result.trufflehog) == 1

    @pytest.mark.asyncio
    async def test_scan_deletes_sandbox_on_success(self):
        sandbox = _make_mock_sandbox()
        with _patch_daytona(sandbox):
            runner = SandboxedScanRunner(snapshot="test-snap", github_token="tok")
            await runner.scan("https://github.com/org/repo")
        sandbox.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_deletes_sandbox_on_clone_failure(self):
        sandbox = _make_mock_sandbox(clone_exit=128)
        sandbox.process.exec = AsyncMock(
            return_value=MagicMock(exit_code=128, result="fatal: not found")
        )
        with _patch_daytona(sandbox):
            runner = SandboxedScanRunner(snapshot="test-snap", github_token="tok")
            with pytest.raises(RuntimeError, match="git clone failed"):
                await runner.scan("https://github.com/org/repo")
        sandbox.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_injects_github_token_in_create(self):
        sandbox = _make_mock_sandbox()
        mock_daytona = AsyncMock()
        mock_daytona.create = AsyncMock(return_value=sandbox)
        mock_daytona.__aenter__ = AsyncMock(return_value=mock_daytona)
        mock_daytona.__aexit__ = AsyncMock(return_value=False)
        with patch("scanners.sandboxed_runner.AsyncDaytona", return_value=mock_daytona):
            runner = SandboxedScanRunner(snapshot="snap", github_token="mytoken")
            await runner.scan("https://github.com/org/repo")
        call_kwargs = mock_daytona.create.call_args[0][0]
        assert call_kwargs.env_vars["GITHUB_TOKEN"] == "mytoken"

    @pytest.mark.asyncio
    async def test_scan_uploads_semgrep_rules(self):
        sandbox = _make_mock_sandbox()
        with _patch_daytona(sandbox):
            runner = SandboxedScanRunner(snapshot="snap", github_token="tok")
            await runner.scan("https://github.com/org/repo")
        assert sandbox.fs.upload_file.call_count == 3

    @pytest.mark.asyncio
    async def test_scan_strips_workspace_prefix_from_file_paths(self):
        th_line = json.dumps({
            "DetectorName": "AWS",
            "Verified": True,
            "SourceMetadata": {"Data": {"Git": {"file": "/workspace/src/config.py", "line": 1}}},
        })
        sandbox = _make_mock_sandbox(th_output=th_line)
        with _patch_daytona(sandbox):
            runner = SandboxedScanRunner(snapshot="snap", github_token="tok")
            result = await runner.scan("https://github.com/org/repo", git_sha="abc")
        assert result.trufflehog[0].file_path == "src/config.py"

    @pytest.mark.asyncio
    async def test_scan_continues_if_one_tool_crashes(self):
        sandbox = AsyncMock()
        sandbox.fs.upload_file = AsyncMock(return_value=None)
        sandbox.delete = AsyncMock()
        sandbox.process.exec = AsyncMock(side_effect=[
            MagicMock(exit_code=0, result=""),
            MagicMock(exit_code=2, result="trufflehog crash"),
            MagicMock(exit_code=0, result=_SEMGREP_OUTPUT),
            MagicMock(exit_code=0, result=_CHECKOV_OUTPUT),
        ])
        with _patch_daytona(sandbox):
            runner = SandboxedScanRunner(snapshot="snap", github_token="tok")
            result = await runner.scan("https://github.com/org/repo")
        assert result.trufflehog == []
        assert len(result.semgrep) == 1
        assert len(result.checkov) == 1


class TestSandboxedScanRunnerScanFile:
    @pytest.mark.asyncio
    async def test_scan_file_returns_checkov_findings(self):
        sandbox = AsyncMock()
        sandbox.fs.upload_file = AsyncMock(return_value=None)
        sandbox.delete = AsyncMock()
        sandbox.process.exec = AsyncMock(side_effect=[
            MagicMock(exit_code=0, result=""),
            MagicMock(exit_code=1, result=_CHECKOV_OUTPUT),
        ])
        with _patch_daytona(sandbox):
            runner = SandboxedScanRunner(snapshot="snap", github_token="tok")
            result = await runner.scan_file(
                "https://github.com/org/repo", "infra/main.tf", git_sha="abc"
            )
        assert isinstance(result, ScanResult)
        assert len(result.checkov) == 1
        assert result.semgrep == []
        assert result.trufflehog == []

    @pytest.mark.asyncio
    async def test_scan_file_runs_checkov_on_correct_path(self):
        sandbox = AsyncMock()
        sandbox.fs.upload_file = AsyncMock(return_value=None)
        sandbox.delete = AsyncMock()
        sandbox.process.exec = AsyncMock(side_effect=[
            MagicMock(exit_code=0, result=""),
            MagicMock(exit_code=0, result='{"check_type":"terraform","results":{"failed_checks":[]}}'),
        ])
        with _patch_daytona(sandbox):
            runner = SandboxedScanRunner(snapshot="snap", github_token="tok")
            await runner.scan_file("https://github.com/org/repo", "infra/main.tf")
        checkov_call = sandbox.process.exec.call_args_list[1]
        assert "/workspace/infra/main.tf" in checkov_call[0][0]

    @pytest.mark.asyncio
    async def test_scan_file_deletes_sandbox_on_error(self):
        sandbox = AsyncMock()
        sandbox.fs.upload_file = AsyncMock(return_value=None)
        sandbox.delete = AsyncMock()
        sandbox.process.exec = AsyncMock(
            return_value=MagicMock(exit_code=128, result="fatal: not found")
        )
        with _patch_daytona(sandbox):
            runner = SandboxedScanRunner(snapshot="snap", github_token="tok")
            with pytest.raises(RuntimeError):
                await runner.scan_file("https://github.com/org/repo", "infra/main.tf")
        sandbox.delete.assert_called_once()


# ---------------------------------------------------------------------------
# DevTeamAgent integration — verify it calls SandboxedScanRunner.scan()
# ---------------------------------------------------------------------------

from agents.dev_team_agent import DevTeamAgent


class TestDevTeamAgentUsesSandboxedRunner:
    @pytest.mark.asyncio
    async def test_handle_event_calls_sandboxed_scan(self):
        agent = DevTeamAgent()
        fake_result = ScanResult(
            trufflehog=[_make_trufflehog_finding()],
        )
        event = {
            "event_type": "push",
            "repo": "org/myrepo",
            "sha": "deadbeef",
        }
        with (
            patch("agents.dev_team_agent.SandboxedScanRunner") as MockRunner,
            patch("agents.dev_team_agent.run_remediation_loop", new_callable=AsyncMock) as mock_loop,
            patch("agents.dev_team_agent.log_event", new_callable=AsyncMock),
            patch("agents.dev_team_agent.get_session") as mock_session,
            patch("agents.dev_team_agent.retrieve_by_control_id", new_callable=AsyncMock),
        ):
            mock_runner_instance = AsyncMock()
            mock_runner_instance.scan.return_value = fake_result
            MockRunner.return_value = mock_runner_instance

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value = mock_ctx

            mock_loop.return_value = MagicMock(status="REMEDIATED")

            import os
            with patch.dict(os.environ, {"GITHUB_TOKEN": "tok"}):
                await agent.handle_event("github.prs", event)

        mock_runner_instance.scan.assert_called_once_with(
            "https://github.com/org/myrepo", git_sha="deadbeef"
        )
        assert mock_loop.call_count == 1


# ---------------------------------------------------------------------------
# PolicyAgent integration — verify it calls SandboxedScanRunner.scan_file()
# ---------------------------------------------------------------------------

from agents.policy_agent import PolicyAgent


class TestPolicyAgentUsesSandboxedRunner:
    @pytest.mark.asyncio
    async def test_handle_tf_plan_calls_scan_file(self):
        agent = PolicyAgent()
        fake_result = ScanResult(checkov=[_make_checkov_finding()])
        event = {
            "file_path": "/local/main.tf",
            "repo_file_path": "infra/main.tf",
            "git_sha": "deadbeef",
        }
        with (
            patch("agents.policy_agent.SandboxedScanRunner") as MockRunner,
            patch("agents.policy_agent.run_remediation_loop", new_callable=AsyncMock) as mock_loop,
            patch("agents.policy_agent.GITHUB_TOKEN", "tok"),
            patch("agents.policy_agent.GITHUB_OWNER", "myorg"),
            patch("agents.policy_agent.GITHUB_REPO", "myrepo"),
        ):
            mock_runner_instance = AsyncMock()
            mock_runner_instance.scan_file.return_value = fake_result
            MockRunner.return_value = mock_runner_instance
            mock_loop.return_value = MagicMock(status="REMEDIATED")

            await agent.handle_event("tf.plans", event)

        mock_runner_instance.scan_file.assert_called_once_with(
            "https://github.com/myorg/myrepo",
            "infra/main.tf",
            git_sha="deadbeef",
        )
        assert mock_loop.call_count == 1


# ---------------------------------------------------------------------------
# Input validation security tests
# ---------------------------------------------------------------------------

class TestValidateRepoUrl:
    def test_accepts_valid_github_url(self):
        _validate_repo_url("https://github.com/org/repo")

    def test_accepts_url_with_hyphens_and_dots(self):
        _validate_repo_url("https://github.com/my-org/my.repo")

    def test_rejects_shell_metacharacters(self):
        with pytest.raises(ValueError):
            _validate_repo_url("https://github.com/org/repo; rm -rf /")

    def test_rejects_command_substitution(self):
        with pytest.raises(ValueError):
            _validate_repo_url("https://github.com/org/repo$(evil)")

    def test_rejects_non_github_url(self):
        with pytest.raises(ValueError):
            _validate_repo_url("https://evil.com/org/repo")

    def test_rejects_path_traversal_in_url(self):
        with pytest.raises(ValueError):
            _validate_repo_url("https://github.com/../etc/passwd")

    def test_rejects_http(self):
        with pytest.raises(ValueError):
            _validate_repo_url("http://github.com/org/repo")


class TestValidateFilePath:
    def test_accepts_simple_path(self):
        _validate_file_path("infra/main.tf")

    def test_accepts_nested_path(self):
        _validate_file_path("terraform/prod/main.tf")

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError):
            _validate_file_path("../../etc/passwd")

    def test_rejects_shell_metacharacters(self):
        with pytest.raises(ValueError):
            _validate_file_path("infra/main.tf; rm -rf /")

    def test_rejects_leading_dash(self):
        with pytest.raises(ValueError):
            _validate_file_path("-dangerous-flag")

    def test_rejects_absolute_path(self):
        with pytest.raises(ValueError):
            _validate_file_path("/etc/passwd")

    def test_rejects_embedded_traversal(self):
        with pytest.raises(ValueError):
            _validate_file_path("infra/../../../etc/passwd")
