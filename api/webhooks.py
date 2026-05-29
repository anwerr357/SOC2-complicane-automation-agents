"""
api/webhooks.py
───────────────
FastAPI application — the single entry point for all inbound events.

Endpoints
─────────
GET  /healthz                — liveness probe for Docker / K8s
GET  /readyz                 — readiness probe (DB + Redis connection check)
POST /webhook/github         — GitHub webhook (push, pull_request events)
POST /webhook/prometheus     — Alertmanager webhook
POST /scan/checkov           — Manual trigger: scan a single IaC file
GET  /evidence               — Recent evidence events (dashboard use)
GET  /evidence/{control_id}  — Events filtered by SOC 2 control

Startup / shutdown
──────────────────
The FastAPI `lifespan` context manager handles:
  - Postgres connection pool initialisation (init_db)
  - Redis connection (future: consumer group creation)

All handler functions are async.  Blocking work (subprocess calls, DB
writes) is awaited and never executed on the event-loop thread directly.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from scanners.checkov_runner import run_checkov
from store.evidence import (
    close_db,
    get_recent_events,
    get_events_by_control,
    get_session,
    init_db,
    log_event,
)

# ── Logging ────────────────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
log = structlog.get_logger(__name__)


# ── Configuration (from environment) ──────────────────────────────────────

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://soc2:soc2secret@localhost:5432/compliance",
)
GITHUB_WEBHOOK_SECRET: str = os.environ.get("GITHUB_WEBHOOK_SECRET", "")


# ── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise infrastructure connections on startup, clean up on shutdown."""
    log.info("Starting SOC 2 Compliance Agent API…")
    await init_db(DATABASE_URL)
    log.info("Database ready.")
    yield
    log.info("Shutting down — closing database pool…")
    await close_db()


# ── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SOC 2 Compliance Agent",
    description=(
        "Event-driven compliance automation system.  "
        "Receives infrastructure change events and coordinates "
        "three specialized agents to detect and remediate SOC 2 violations."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health endpoints ───────────────────────────────────────────────────────

@app.get("/healthz", tags=["ops"])
async def healthz() -> dict[str, str]:
    """Liveness probe — always 200 if the process is alive."""
    return {"status": "alive"}


@app.get("/readyz", tags=["ops"])
async def readyz() -> dict[str, str]:
    """Readiness probe — checks DB connectivity."""
    try:
        async with get_session() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        log.error("Readiness check failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not ready: {exc}",
        )


# ── GitHub webhook ─────────────────────────────────────────────────────────

def _verify_github_signature(body: bytes, signature_header: str | None) -> None:
    """
    Validate the X-Hub-Signature-256 header from GitHub.
    Raises HTTP 401 if the signature does not match or the secret is wrong.
    """
    if not GITHUB_WEBHOOK_SECRET:
        log.warning("GITHUB_WEBHOOK_SECRET not set — skipping signature check")
        return

    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed X-Hub-Signature-256 header.",
        )

    expected = (
        "sha256=" +
        hmac.new(
            GITHUB_WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub signature mismatch.",
        )


@app.post("/webhook/github", tags=["webhooks"])
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
) -> JSONResponse:
    """
    Receive GitHub push and pull_request events.

    On `push`: the Dev Team Agent will be triggered to run Trufflehog +
    Semgrep on the changed files (Week 2+).

    On `pull_request` (opened/synchronize): same scanner pipeline.
    """
    body = await request.body()
    _verify_github_signature(body, x_hub_signature_256)

    payload: dict[str, Any] = await request.json()
    event_type = x_github_event or "unknown"

    log.info(
        "Received GitHub webhook",
        event_type=event_type,
        repo=payload.get("repository", {}).get("full_name"),
    )

    # TODO (Week 2): publish to Redis Stream `github.prs` and hand off to
    # the Dev Team Agent.  For now we acknowledge and return.
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "received": True,
            "event_type": event_type,
            "message": "Event queued for processing.",
        },
    )


# ── Prometheus / Alertmanager webhook ─────────────────────────────────────

@app.post("/webhook/prometheus", tags=["webhooks"])
async def prometheus_webhook(request: Request) -> JSONResponse:
    """
    Receive Alertmanager firing alerts.

    Maps Prometheus alert labels to SOC 2 controls and publishes to the
    `prometheus.alerts` Redis Stream (Week 4+).
    """
    payload = await request.json()
    alerts = payload.get("alerts", [])
    log.info("Received %d Prometheus alert(s)", len(alerts))
    # TODO (Week 4): forward to Redis Stream `prometheus.alerts`
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"received": True, "alert_count": len(alerts)},
    )


# ── Manual scan trigger ────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    file_path: str = Field(
        ...,
        description="Absolute or relative path to a Terraform .tf or K8s YAML file.",
        examples=["tests/fixtures/demo.tf"],
    )
    git_sha: str | None = Field(
        default=None,
        description="Optional git commit SHA for audit attribution.",
    )


class FindingResponse(BaseModel):
    check_id: str
    control_id: str
    control_name: str
    resource_name: str
    file_path: str
    severity: str
    git_sha: str | None


@app.post(
    "/scan/checkov",
    response_model=list[FindingResponse],
    tags=["scanning"],
)
async def scan_checkov(req: ScanRequest) -> list[FindingResponse]:
    """
    Manually trigger a Checkov scan and log all violations to the evidence store.

    This endpoint is used for:
    - Development testing against demo Terraform files
    - CI pipeline integration (Week 6)
    - Ad-hoc scans triggered by engineers

    Returns the list of violations found (may be empty if all checks pass).
    """
    path = Path(req.file_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {req.file_path}",
        )

    log.info("Running Checkov scan", file=str(path))
    findings = await run_checkov(path, git_sha=req.git_sha)

    # Persist every finding to the evidence store
    async with get_session() as session:
        for finding in findings:
            await log_event(session, finding.to_evidence_dict())

    log.info("Checkov scan complete", violations=len(findings))

    return [
        FindingResponse(
            check_id=f.check_id,
            control_id=f.control_id,
            control_name=f.control_name,
            resource_name=f.resource_name,
            file_path=f.file_path,
            severity=f.severity,
            git_sha=f.git_sha,
        )
        for f in findings
    ]


# ── Evidence read API ──────────────────────────────────────────────────────

@app.get("/evidence", tags=["evidence"])
async def list_evidence(limit: int = 50) -> list[dict]:
    """
    Return the `limit` most recent evidence events.

    Used by the React dashboard (Week 6).
    """
    async with get_session() as session:
        events = await get_recent_events(session, limit=limit)
    return [
        {
            "id":                   str(e.id),
            "created_at":           e.created_at.isoformat(),
            "agent_name":           e.agent_name,
            "scanner_used":         e.scanner_used,
            "check_id":             e.check_id,
            "control_id":           e.control_id,
            "control_name":         e.control_name,
            "resource_name":        e.resource_name,
            "file_path":            e.file_path,
            "severity":             e.severity,
            "status":               e.status,
            "pr_url":               e.pr_url,
            "violation_description": e.violation_description,
        }
        for e in events
    ]


@app.get("/evidence/{control_id}", tags=["evidence"])
async def evidence_by_control(control_id: str) -> list[dict]:
    """
    Return all evidence events for a specific SOC 2 control (e.g. `CC6.7`).
    """
    async with get_session() as session:
        events = await get_events_by_control(session, control_id)
    return [
        {
            "id":           str(e.id),
            "created_at":   e.created_at.isoformat(),
            "check_id":     e.check_id,
            "control_id":   e.control_id,
            "resource_name": e.resource_name,
            "file_path":    e.file_path,
            "severity":     e.severity,
            "status":       e.status,
            "pr_url":       e.pr_url,
        }
        for e in events
    ]
