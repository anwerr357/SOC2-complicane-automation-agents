"""
brain/llm.py
────────────
Claude API client — shared by all three agents.

All LLM calls in this system go through this module.  It enforces:
  - Structured JSON output mode (every response is parsed before returning)
  - Prompt caching on the SOC 2 control context (stays warm across calls)
  - Consistent error handling and retry logic

Implemented in Week 3 when the compliance brain is wired up.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

# TODO (Week 3): implement using the Anthropic SDK with prompt caching
# See: /skill claude-api for SDK patterns

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
