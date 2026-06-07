"""Tests for validate_remediation — the re-scan step of the loop."""
from __future__ import annotations

import shutil

import pytest

from mutate.validate import validate_remediation

requires_checkov = pytest.mark.skipif(
    shutil.which("checkov") is None, reason="checkov CLI not installed"
)

UNENCRYPTED_TF = '''
resource "aws_s3_bucket" "app_data" {
  bucket = "my-app-data"
}
'''

ENCRYPTED_TF = '''
resource "aws_s3_bucket" "app_data" {
  bucket = "my-app-data"
}
resource "aws_s3_bucket_server_side_encryption_configuration" "app_data_sse" {
  bucket = aws_s3_bucket.app_data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}
'''


@pytest.mark.asyncio
async def test_trufflehog_secret_removed_returns_true():
    finding = {
        "scanner_used": "trufflehog",
        "check_id": "TRUFFLEHOG_AWS",
        "file_path": "config.py",
        "raw_finding": {"Raw": "AKIAIOSFODNN7EXAMPLE"},
    }
    patched = 'AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]\n'
    assert await validate_remediation(finding, patched) is True


@pytest.mark.asyncio
async def test_trufflehog_secret_still_present_returns_false():
    finding = {
        "scanner_used": "trufflehog",
        "check_id": "TRUFFLEHOG_AWS",
        "file_path": "config.py",
        "raw_finding": {"Raw": "AKIAIOSFODNN7EXAMPLE"},
    }
    patched = 'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n'
    assert await validate_remediation(finding, patched) is False


@requires_checkov
@pytest.mark.asyncio
async def test_checkov_fixed_file_returns_true():
    # Pick a CC6.7 check id that the encrypted file actually *satisfies*: one
    # that fires on the unencrypted fixture but no longer fires once the
    # encryption block is added. (The unencrypted file trips several unrelated
    # CC6.7 checks — public-access-block, lifecycle — that encryption does not
    # fix, so we must select the check the patch genuinely resolves rather than
    # just the first CC6.7 check.) This is version-agnostic across checkov.
    unenc = await run_checkov_string(UNENCRYPTED_TF)
    enc = await run_checkov_string(ENCRYPTED_TF)
    unenc_cc67 = {f.check_id for f in unenc if f.control_id == "CC6.7"}
    enc_cc67 = {f.check_id for f in enc if f.control_id == "CC6.7"}
    fixed_checks = sorted(unenc_cc67 - enc_cc67)
    assert fixed_checks, "encryption block should resolve at least one CC6.7 check"
    finding = {
        "scanner_used": "checkov",
        "check_id": fixed_checks[0],
        "file_path": "main.tf",
        "raw_finding": {},
    }
    assert await validate_remediation(finding, ENCRYPTED_TF) is True


# Helper used by the checkov test: scan a string by writing it to a temp .tf
async def run_checkov_string(content: str):
    import tempfile
    from pathlib import Path
    from scanners.checkov_runner import run_checkov
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "main.tf"
        p.write_text(content)
        return await run_checkov(p)
