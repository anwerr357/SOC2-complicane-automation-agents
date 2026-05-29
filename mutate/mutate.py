"""
mutate/mutate.py
────────────────
Remediation mutator — the "M" in the 5-step loop.

Steps (Week 2 implementation):
  1. Fetch the violating file from GitHub via PyGithub
  2. Send file content + violation description to Claude API
  3. Claude returns the patched file content (structured JSON)
  4. Create a new branch: compliance-fix/<control_id>/<check_id>
  5. Push the patched blob as a new commit
  6. Open a PR with:
     - Title: "[CC6.7] Fix: S3 bucket encryption missing on aws_s3_bucket.app_data"
     - Body: LLM-generated plain-English explanation + control text from RAG
     - Labels: ["compliance-fix"]

GitOps principle: mutations NEVER apply directly to the cluster.
Every fix goes through a pull request for human review.
"""

from __future__ import annotations

# TODO (Week 2): implement open_remediation_pr(finding, control_text) -> str
# Returns the PR URL
