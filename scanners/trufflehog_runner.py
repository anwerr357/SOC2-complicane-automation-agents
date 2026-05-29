"""
scanners/trufflehog_runner.py
──────────────────────────────
Async subprocess wrapper around the Trufflehog secret scanner.

Trufflehog scans entire git history using:
  - 700+ regex patterns for known secret formats (AWS, GCP, GitHub, etc.)
  - Shannon entropy analysis for unknown high-entropy strings
  - Live verification — only reports secrets that are actually active

Maps to SOC 2 controls: CC6.1 (logical access), CC6.2 (authentication).

Implemented in Week 3.
"""

from __future__ import annotations

# TODO (Week 3): implement TrufflehogRunner with the same interface as
# CheckovRunner — scan(repo_path, git_sha) -> list[TrufflehogFinding]
