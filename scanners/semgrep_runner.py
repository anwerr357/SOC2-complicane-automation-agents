"""
scanners/semgrep_runner.py
──────────────────────────
Async subprocess wrapper around Semgrep SAST scanner.

Semgrep uses AST-based pattern matching with custom rules.
Key custom rule: any function calling a DB write method must also call
audit_log() — violation maps to CC7.2.

Implemented in Week 3.
"""

from __future__ import annotations

# TODO (Week 3): implement SemgrepRunner with custom rule YAML loading
# and the same interface as CheckovRunner
