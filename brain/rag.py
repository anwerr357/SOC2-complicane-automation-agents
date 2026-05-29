"""
brain/rag.py
────────────
RAG retrieval pipeline — queries Qdrant to retrieve relevant SOC 2 control
text given a violation description.

Implemented in Week 3.
"""

from __future__ import annotations

# TODO (Week 3): implement retrieve_control(violation_text: str) -> str
# that queries the Qdrant "soc2_controls" collection and returns the
# top-1 matching control text for prompt augmentation.
