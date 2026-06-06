"""
mutate/mutate.py
────────────────
Remediation mutator — step 4 of the 5-step compliance loop.

Week 3 upgrade
──────────────
Step 2 now tries LLM-based patching first (brain/llm.generate_patch).
If the LLM call fails or no API key is configured, falls back to the
rule-based PATCH_REGISTRY functions from Week 2.  Interface is unchanged.

What open_remediation_pr() does
────────────────────────────────
1. Fetch the violating file content from GitHub (current HEAD)
2. Patch the file:
     a. Try LLM  → generate_patch(file, finding, control_text)
     b. Fallback → PATCH_REGISTRY[check_id](content, resource_name)
3. Create branch:  compliance-fix/<control_id>/<check_id>
4. Push the patched file as a single commit
5. Open a PR:
     title:  [CC6.7] Fix: S3 encryption missing on aws_s3_bucket.app_data
     body:   LLM-generated explanation + changes summary + SOC 2 reference
     label:  compliance-fix  (created if it doesn't exist)
6. Return the PR URL so the caller can store it in the evidence table

GitOps principle
────────────────
Fixes NEVER apply directly to the repo default branch.
Every remediation goes through a pull request — humans stay in the loop.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from github import Auth, Github, GithubException
from github.Repository import Repository

from brain.llm import generate_patch

log = logging.getLogger(__name__)


# ── PR label ──────────────────────────────────────────────────────────────

COMPLIANCE_LABEL = "compliance-fix"
LABEL_COLOR      = "d73a4a"   # red — high-visibility in the PR list


# ── Rule-based patches ────────────────────────────────────────────────────
# Each function receives the full file content as a string and returns the
# patched content.  They use regex substitution so they work on any resource
# name without hardcoding.
#
# Week 3: replace these with a single LLM call that understands context.

def _patch_s3_encryption(content: str, resource_name: str) -> str:
    """
    Add aws_s3_bucket_server_side_encryption_configuration block.
    Fixes: CKV_AWS_19, CKV2_AWS_6, CKV2_AWS_60, CKV2_AWS_61, CKV2_AWS_62
    """
    # Extract bare resource label (e.g. "aws_s3_bucket.app_data" → "app_data")
    label = resource_name.split(".")[-1] if "." in resource_name else resource_name

    patch = f'''
resource "aws_s3_bucket_server_side_encryption_configuration" "{label}_sse" {{
  bucket = aws_s3_bucket.{label}.id

  rule {{
    apply_server_side_encryption_by_default {{
      sse_algorithm = "aws:kms"
    }}
    bucket_key_enabled = true
  }}
}}
'''
    return content + patch


def _patch_s3_logging(content: str, resource_name: str) -> str:
    """
    Add aws_s3_bucket_logging resource.
    Fixes: CKV_AWS_18
    """
    label = resource_name.split(".")[-1] if "." in resource_name else resource_name

    patch = f'''
resource "aws_s3_bucket_logging" "{label}_logging" {{
  bucket = aws_s3_bucket.{label}.id

  target_bucket = aws_s3_bucket.{label}.id
  target_prefix = "access-logs/"
}}
'''
    return content + patch


def _patch_kms_rotation(content: str, resource_name: str) -> str:
    """
    Enable key rotation on aws_kms_key.
    Fixes: CKV_AWS_7
    """
    # Find the kms key block and add enable_key_rotation = true
    pattern = r'(resource\s+"aws_kms_key"\s+"[^"]+"\s*\{)'
    replacement = r'\1\n  enable_key_rotation = true'
    patched = re.sub(pattern, replacement, content)
    if patched == content:
        # Block not matched — append a comment so the engineer knows
        patched += "\n# TODO: add enable_key_rotation = true to your aws_kms_key resource\n"
    return patched


def _patch_dynamodb_encryption(content: str, resource_name: str) -> str:
    """
    Add server_side_encryption block to aws_dynamodb_table.
    Fixes: CKV_AWS_119
    """
    pattern = r'(resource\s+"aws_dynamodb_table"\s+"[^"]+"\s*\{)'
    replacement = (
        r'\1\n'
        r'  server_side_encryption {\n'
        r'    enabled = true\n'
        r'  }'
    )
    patched = re.sub(pattern, replacement, content)
    if patched == content:
        patched += "\n# TODO: add server_side_encryption { enabled = true } to your aws_dynamodb_table resource\n"
    return patched


def _patch_iam_wildcard(content: str, resource_name: str) -> str:
    """
    Replace wildcard Action/Resource with least-privilege placeholders.
    Fixes: CKV_AWS_40, CKV_AWS_274, CKV_AWS_289, CKV_AWS_290, CKV_AWS_355
    """
    # Replace "Action": "*" with a restricted placeholder
    patched = re.sub(
        r'"Action"\s*:\s*"\*"',
        '"Action": ["s3:GetObject", "s3:PutObject"]  # TODO: restrict to minimum required actions',
        content,
    )
    # Replace "Resource": "*" with a restricted placeholder
    patched = re.sub(
        r'"Resource"\s*:\s*"\*"',
        '"Resource": "arn:aws:s3:::your-bucket/*"  # TODO: restrict to specific resource ARN',
        patched,
    )
    return patched


# Maps check_id → patch function
PATCH_REGISTRY: dict[str, callable] = {
    # CC6.7 — Encryption at rest
    "CKV_AWS_19":   _patch_s3_encryption,
    "CKV2_AWS_6":   _patch_s3_encryption,
    "CKV2_AWS_60":  _patch_s3_encryption,
    "CKV2_AWS_61":  _patch_s3_encryption,
    "CKV2_AWS_62":  _patch_s3_encryption,
    "CKV_AWS_119":  _patch_dynamodb_encryption,
    "CKV_AWS_7":    _patch_kms_rotation,
    # CC7.1 — Monitoring / logging
    "CKV_AWS_18":   _patch_s3_logging,
    # CC6.1 / CC6.6 — Least privilege
    "CKV_AWS_40":   _patch_iam_wildcard,
    "CKV_AWS_274":  _patch_iam_wildcard,
    "CKV_AWS_289":  _patch_iam_wildcard,
    "CKV_AWS_290":  _patch_iam_wildcard,
    "CKV_AWS_355":  _patch_iam_wildcard,
}


# ── Rule-based patch helper ────────────────────────────────────────────────

def _apply_rule_patch(
    content: str,
    check_id: str,
    resource_name: str,
) -> tuple[str, bool, str]:
    """
    Apply a hardcoded patch from PATCH_REGISTRY.

    Returns (patched_content, patched_flag, changes_summary).
    Used as fallback when the LLM patch is unavailable or fails.
    """
    patch_fn = PATCH_REGISTRY.get(check_id)
    if patch_fn is None:
        log.warning(
            "No rule-based patch for %s — PR will document the issue only.",
            check_id,
        )
        return content, False, "No automated fix available — manual remediation required."

    patched = patch_fn(content, resource_name)
    summary = f"Applied rule-based fix for {check_id} on {resource_name}."
    log.info("Rule-based patch applied for %s", check_id)
    return patched, True, summary


# ── Result dataclass ───────────────────────────────────────────────────────

@dataclass
class RemediationResult:
    """Returned by open_remediation_pr() on success."""
    pr_url:    str
    pr_number: int
    branch:    str
    patched:   bool   # False if no patch function exists for this check_id


# ── Main function ──────────────────────────────────────────────────────────

async def open_remediation_pr(
    *,
    github_token: str,
    repo_full_name: str,          # e.g. "anwerr357/travel-App"
    file_path: str,               # path inside the repo, e.g. "infra/main.tf"
    check_id: str,                # e.g. "CKV2_AWS_61"
    control_id: str,              # e.g. "CC6.7"
    control_name: str,            # e.g. "Encryption at rest"
    resource_name: str,           # e.g. "aws_s3_bucket.app_data"
    severity: str,                # e.g. "MEDIUM"
    violation_description: str = "",
    control_text: str = "",       # SOC 2 control text from Qdrant — used by LLM patcher
) -> RemediationResult:
    """
    Open a GitHub pull request that fixes a single Checkov violation.

    Parameters
    ──────────
    github_token      : Personal access token with repo scope
    repo_full_name    : "owner/repo"
    file_path         : path to the file inside the repo
    check_id          : Checkov check that failed
    control_id        : SOC 2 control the check maps to
    control_name      : human-readable control label
    resource_name     : the resource that violated (e.g. aws_s3_bucket.app_data)
    severity          : HIGH | MEDIUM | LOW | INFO
    violation_description : plain-English description (empty until Week 3 LLM)

    Returns
    ───────
    RemediationResult with pr_url, pr_number, branch name, patched flag.

    Raises
    ──────
    GithubException  if the GitHub API call fails
    ValueError       if the file cannot be fetched from the repo
    """
    g = Github(auth=Auth.Token(github_token))
    repo: Repository = g.get_repo(repo_full_name)

    # ── 1. Fetch current file content ──────────────────────────────────────
    log.info("Fetching %s from %s", file_path, repo_full_name)
    try:
        file_obj  = repo.get_contents(file_path)
        original  = file_obj.decoded_content.decode("utf-8")
        file_sha  = file_obj.sha          # needed for the update API call
    except GithubException as exc:
        raise ValueError(
            f"Could not fetch {file_path} from {repo_full_name}: {exc}"
        ) from exc

    # ── 2. Apply patch ─────────────────────────────────────────────────────
    # Try LLM first (Week 3). Fall back to PATCH_REGISTRY (Week 2) if:
    #   - no control_text was passed (RAG not available)
    #   - LLM call failed (bad key, timeout, etc.)
    #   - LLM returned the file unchanged (used_llm=False)

    changes_summary = ""

    if control_text:
        llm_result = await generate_patch(
            file_content=original,
            check_id=check_id,
            control_id=control_id,
            control_name=control_name,
            control_text=control_text,
            resource_name=resource_name,
            file_path=file_path,
        )
        if llm_result.used_llm:
            patched_content = llm_result.patched_content
            changes_summary = llm_result.changes_summary
            patched = True
            log.info("LLM patch applied for %s — %s", check_id, changes_summary)
        else:
            log.warning("LLM patch failed for %s — falling back to rule-based.", check_id)
            patched_content, patched, changes_summary = _apply_rule_patch(
                original, check_id, resource_name
            )
    else:
        patched_content, patched, changes_summary = _apply_rule_patch(
            original, check_id, resource_name
        )

    # ── 3. Create branch ───────────────────────────────────────────────────
    # Branch name: compliance-fix/CC6.7/CKV2_AWS_61
    safe_control = control_id.replace(".", "-")
    branch_name  = f"compliance-fix/{safe_control}/{check_id}"

    default_branch = repo.get_branch(repo.default_branch)
    base_sha       = default_branch.commit.sha

    try:
        repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base_sha,
        )
        log.info("Created branch %s", branch_name)
    except GithubException as exc:
        if exc.status == 422:
            # Branch already exists — that's fine, reuse it
            log.warning("Branch %s already exists — reusing.", branch_name)
        else:
            raise

    # ── 4. Push patched file ───────────────────────────────────────────────
    commit_message = (
        f"fix({control_id}): remediate {check_id} on {resource_name}\n\n"
        f"Automated compliance fix by SOC 2 Compliance Agent.\n"
        f"Control: {control_id} — {control_name}\n"
        f"Scanner: Checkov {check_id}\n"
        f"Severity: {severity}"
    )

    repo.update_file(
        path=file_path,
        message=commit_message,
        content=patched_content,
        sha=file_sha,
        branch=branch_name,
    )
    log.info("Pushed patched file to branch %s", branch_name)

    # ── 5. Ensure compliance-fix label exists ──────────────────────────────
    _ensure_label(repo)

    # ── 6. Open pull request ───────────────────────────────────────────────
    pr_title = f"[{control_id}] Fix: {_short_description(check_id, resource_name)}"
    pr_body  = _build_pr_body(
        check_id=check_id,
        control_id=control_id,
        control_name=control_name,
        resource_name=resource_name,
        file_path=file_path,
        severity=severity,
        violation_description=violation_description,
        patched=patched,
        changes_summary=changes_summary,
    )

    pr = repo.create_pull(
        title=pr_title,
        body=pr_body,
        head=branch_name,
        base=repo.default_branch,
    )

    # Add label
    try:
        pr.add_to_labels(COMPLIANCE_LABEL)
    except GithubException:
        pass   # label add is best-effort

    log.info(
        "Opened PR #%d: %s — %s",
        pr.number, pr_title, pr.html_url,
    )

    return RemediationResult(
        pr_url=pr.html_url,
        pr_number=pr.number,
        branch=branch_name,
        patched=patched,
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _ensure_label(repo: Repository) -> None:
    """Create the compliance-fix label if it doesn't exist yet."""
    try:
        repo.get_label(COMPLIANCE_LABEL)
    except GithubException:
        try:
            repo.create_label(
                name=COMPLIANCE_LABEL,
                color=LABEL_COLOR,
                description="Automated SOC 2 compliance remediation",
            )
            log.info("Created label '%s' on repo.", COMPLIANCE_LABEL)
        except GithubException:
            pass   # best-effort


def _short_description(check_id: str, resource_name: str) -> str:
    """One-line description for the PR title."""
    descriptions = {
        "CKV_AWS_19":  "S3 bucket encryption missing",
        "CKV2_AWS_6":  "S3 bucket encryption missing",
        "CKV2_AWS_60": "S3 bucket encryption missing",
        "CKV2_AWS_61": "S3 bucket encryption missing",
        "CKV2_AWS_62": "S3 bucket encryption missing",
        "CKV_AWS_18":  "S3 access logging not enabled",
        "CKV_AWS_7":   "KMS key rotation not enabled",
        "CKV_AWS_119": "DynamoDB table encryption missing",
        "CKV_AWS_40":  "IAM policy uses wildcard permissions",
        "CKV_AWS_274": "IAM policy uses wildcard permissions",
        "CKV_AWS_289": "IAM policy uses wildcard permissions",
        "CKV_AWS_290": "IAM policy uses wildcard permissions",
        "CKV_AWS_355": "IAM policy uses wildcard permissions",
    }
    base = descriptions.get(check_id, f"{check_id} violation")
    return f"{base} on {resource_name}"


def _build_pr_body(
    *,
    check_id: str,
    control_id: str,
    control_name: str,
    resource_name: str,
    file_path: str,
    severity: str,
    violation_description: str,
    patched: bool,
    changes_summary: str = "",
) -> str:
    """Build the pull request body markdown."""
    patch_note = (
        "This PR applies an automated fix. Please review before merging."
        if patched
        else
        "No automatic patch is available for this check yet. "
        "This PR documents the violation and requires a manual fix."
    )

    description_section = (
        f"\n### Violation explanation\n\n{violation_description}\n"
        if violation_description
        else ""
    )

    changes_section = (
        f"\n### What was changed\n\n{changes_summary}\n"
        if changes_summary
        else ""
    )

    return f"""## SOC 2 Compliance Violation — Automated Remediation

| Field | Value |
|-------|-------|
| **SOC 2 Control** | `{control_id}` — {control_name} |
| **Checkov Check** | `{check_id}` |
| **Severity** | `{severity}` |
| **Resource** | `{resource_name}` |
| **File** | `{file_path}` |
| **Detected by** | SOC 2 Compliance Agent (Policy Agent / Checkov) |
| **Timestamp** | {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} |
{description_section}{changes_section}
---

### What was wrong

The resource `{resource_name}` in `{file_path}` failed Checkov check `{check_id}`,
which maps to SOC 2 Trust Service Criterion **{control_id} ({control_name})**.

### What this PR does

{patch_note}

---

### Review checklist

- [ ] The patched resource configuration looks correct
- [ ] No existing functionality is broken
- [ ] Terraform plan has been reviewed (`terraform plan`)
- [ ] Ready to merge

---
> *Opened automatically by the [SOC 2 Compliance Agent](https://github.com/anwerr357/travel-App).*
"""
