"""
store/evidence.py
─────────────────
Async helper layer that sits between the agents and Postgres.

All writes go through `log_event`.  All reads used by the dashboard and
the remediation loop go through the query helpers below.  We never issue
raw SQL outside this module — everything uses SQLAlchemy 2.0 async style.

Session lifecycle
─────────────────
`get_session` is an async generator that yields a bound `AsyncSession`.
Use it as a dependency in FastAPI routes or as an async context manager
inside agents:

    async with get_session() as session:
        await log_event(session, finding)

Engine initialisation
─────────────────────
Call `init_db()` once at startup (inside the FastAPI lifespan handler).
It creates all tables if they don't yet exist.  Alembic migrations are
used for production schema changes; this is the fast-bootstrap path for
development and CI.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from store.models import Base, EventStatus, EvidenceEvent

log = logging.getLogger(__name__)

# Module-level engine & session factory — initialised by `init_db()`
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


# ── Initialisation ─────────────────────────────────────────────────────────

async def init_db(database_url: str) -> None:
    """
    Create the async engine, run CREATE TABLE IF NOT EXISTS for every model,
    and store the session factory for later use.

    Call once from your FastAPI lifespan or main agent entrypoint.
    """
    global _engine, _session_factory

    _engine = create_async_engine(
        database_url,
        echo=True,          # set True to see every SQL statement
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # drop stale connections automatically
    )

    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,   # keep ORM objects usable after commit
        class_=AsyncSession,
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    log.info("Database initialised — all tables ready.")


async def close_db() -> None:
    """Dispose the engine on shutdown."""
    if _engine:
        await _engine.dispose()
        log.info("Database connection pool closed.")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that yields a transactional session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Write operations ───────────────────────────────────────────────────────

async def log_event(session: AsyncSession, finding: dict) -> EvidenceEvent:
    """
    Persist a scanner finding as a new EvidenceEvent row.

    Parameters
    ──────────
    session  : active AsyncSession (caller owns the transaction)
    finding  : dict with keys matching EvidenceEvent columns.
               Required keys: agent_name, scanner_used, check_id,
               control_id, control_name, resource_name, file_path, severity,
               raw_finding.

    Returns the newly created (and flushed) ORM object.
    """
    event = EvidenceEvent(
        agent_name=finding["agent_name"],
        scanner_used=finding["scanner_used"],
        check_id=finding["check_id"],
        control_id=finding["control_id"],
        control_name=finding["control_name"],
        resource_name=finding["resource_name"],
        file_path=finding["file_path"],
        git_sha=finding.get("git_sha"),
        severity=finding["severity"],
        violation_description=finding.get("violation_description", ""),
        raw_finding=finding["raw_finding"],
        status=EventStatus.OPEN,
    )
    session.add(event)
    await session.flush()   # assign DB-generated id without committing yet
    log.info(
        "Logged evidence event",
        extra={
            "event_id": str(event.id),
            "check_id": event.check_id,
            "control_id": event.control_id,
        },
    )
    return event


async def update_remediation(
    session: AsyncSession,
    event_id: UUID,
    *,
    pr_url: str,
    pr_number: int,
    status: EventStatus = EventStatus.REMEDIATED,
    violation_description: str | None = None,
) -> None:
    """
    Attach a pull-request URL to an existing event and flip its status.
    Called by the mutate layer after a PR is opened. When
    violation_description is given, the stored description is updated too.
    """
    values = {"pr_url": pr_url, "pr_number": pr_number, "status": status}
    if violation_description is not None:
        values["violation_description"] = violation_description
    await session.execute(
        update(EvidenceEvent)
        .where(EvidenceEvent.id == event_id)
        .values(**values)
    )
    log.info("Updated remediation for event %s → PR #%d", event_id, pr_number)


async def escalate_event(
    session: AsyncSession,
    event_id: UUID,
    *,
    violation_description: str | None = None,
) -> None:
    """Mark an event as escalated (max retries exceeded or validation failed).
    When violation_description is given, the stored description is updated too."""
    values = {"status": EventStatus.ESCALATED}
    if violation_description is not None:
        values["violation_description"] = violation_description
    await session.execute(
        update(EvidenceEvent)
        .where(EvidenceEvent.id == event_id)
        .values(**values)
    )
    log.warning("Escalated event %s — human review required.", event_id)


async def increment_remediation_run(
    session: AsyncSession, event_id: UUID
) -> None:
    """Increment the remediation attempt counter on each loop iteration."""
    from sqlalchemy import text

    await session.execute(
        update(EvidenceEvent)
        .where(EvidenceEvent.id == event_id)
        .values(remediation_run=EvidenceEvent.remediation_run + 1)
    )


# ── Read operations ────────────────────────────────────────────────────────

async def get_open_events(session: AsyncSession) -> list[EvidenceEvent]:
    """Return all events that still need remediation."""
    result = await session.execute(
        select(EvidenceEvent)
        .where(EvidenceEvent.status == EventStatus.OPEN)
        .order_by(EvidenceEvent.created_at.desc())
    )
    return list(result.scalars().all())


async def get_events_by_control(
    session: AsyncSession, control_id: str
) -> list[EvidenceEvent]:
    """All events (any status) for a given SOC 2 control."""
    result = await session.execute(
        select(EvidenceEvent)
        .where(EvidenceEvent.control_id == control_id)
        .order_by(EvidenceEvent.created_at.desc())
    )
    return list(result.scalars().all())


async def get_recent_events(
    session: AsyncSession, limit: int = 50
) -> list[EvidenceEvent]:
    """Most recent `limit` events — used by the dashboard API."""
    result = await session.execute(
        select(EvidenceEvent)
        .order_by(EvidenceEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
