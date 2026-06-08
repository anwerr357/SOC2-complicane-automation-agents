"""Tests for the optional violation_description kwarg on the terminal writers."""
from __future__ import annotations

import uuid

import pytest

from store.evidence import escalate_event, update_remediation


class _FakeSession:
    """Captures the statement passed to execute() — no DB needed."""
    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)


def _set_values(stmt) -> dict:
    """Return the SET column->value mapping of an UPDATE statement.

    SQLAlchemy wraps each SET value in a BindParameter, so unwrap `.value`.
    """
    return {
        col.name: getattr(val, "value", val)
        for col, val in stmt._values.items()
    }


@pytest.mark.asyncio
async def test_escalate_without_description_sets_only_status():
    s = _FakeSession()
    await escalate_event(s, uuid.uuid4())
    vals = _set_values(s.statements[0])
    assert "status" in vals
    assert "violation_description" not in vals


@pytest.mark.asyncio
async def test_escalate_with_description_sets_it():
    s = _FakeSession()
    await escalate_event(s, uuid.uuid4(), violation_description="human must fix this")
    vals = _set_values(s.statements[0])
    assert vals["violation_description"] == "human must fix this"


@pytest.mark.asyncio
async def test_update_remediation_with_description_sets_it():
    s = _FakeSession()
    await update_remediation(
        s, uuid.uuid4(), pr_url="http://x/pr/1", pr_number=1,
        violation_description="explained",
    )
    vals = _set_values(s.statements[0])
    assert vals["violation_description"] == "explained"
    assert vals["pr_url"] == "http://x/pr/1"


@pytest.mark.asyncio
async def test_update_remediation_without_description_omits_it():
    s = _FakeSession()
    await update_remediation(s, uuid.uuid4(), pr_url="http://x/pr/1", pr_number=1)
    vals = _set_values(s.statements[0])
    assert "violation_description" not in vals
