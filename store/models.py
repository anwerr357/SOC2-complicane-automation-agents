"""SQLAlchemy ORM for the evidence_events audit table; rows are immutable, status updates in place."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    DateTime,
    Enum,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func



class Base(DeclarativeBase):
    pass



class AgentName(str, PyEnum):
    POLICY = "policy"
    CLUSTER_OPERATOR = "cluster_operator"
    DEV_TEAM = "dev_team"
    MANUAL = "manual"


class ScannerUsed(str, PyEnum):
    CHECKOV = "checkov"
    TRUFFLEHOG = "trufflehog"
    SEMGREP = "semgrep"
    K8S_WATCH = "k8s_watch"
    PROMETHEUS = "prometheus"
    MANUAL = "manual"


class Severity(str, PyEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class EventStatus(str, PyEnum):
    OPEN = "open"
    REMEDIATED = "remediated"
    ESCALATED = "escalated"
    FALSE_POSITIVE = "false_positive"



class EvidenceEvent(Base):
    """One row per compliance violation detected by any agent."""

    __tablename__ = "evidence_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    agent_name: Mapped[str] = mapped_column(
        Enum(AgentName, name="agent_name_enum"),
        nullable=False,
        index=True,
    )
    scanner_used: Mapped[str] = mapped_column(
        Enum(ScannerUsed, name="scanner_used_enum"),
        nullable=False,
        index=True,
    )

    check_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    control_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    control_name: Mapped[str] = mapped_column(String(256), nullable=False)

    resource_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    severity: Mapped[str] = mapped_column(
        Enum(Severity, name="severity_enum"),
        nullable=False,
        index=True,
    )

    violation_description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Raw JSON blob from the scanner — preserved verbatim
    raw_finding: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(EventStatus, name="event_status_enum"),
        nullable=False,
        default=EventStatus.OPEN,
        index=True,
    )
    remediation_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<EvidenceEvent id={self.id!s:.8} "
            f"control={self.control_id} "
            f"check={self.check_id} "
            f"status={self.status}>"
        )
