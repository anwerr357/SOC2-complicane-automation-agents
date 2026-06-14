"""FastAPI app: single entry point for GitHub/Prometheus webhooks, manual scans, and evidence queries."""

from __future__ import annotations

import asyncio
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
    update_remediation,
)
from mutate.mutate import open_remediation_pr
from brain.embeddings import embed_controls
from brain.rag import retrieve_by_control_id
from brain.llm import generate_explanation
from store.redis_streams import init_redis, close_redis, publish
from agents.policy_agent import PolicyAgent
from agents.cluster_operator import ClusterOperatorAgent
from agents.dev_team_agent import DevTeamAgent


LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()

# Shared chain so structlog and plain stdlib records (agents, scanners,
# sqlalchemy) render through one handler — otherwise the agents' getLogger()
# INFO lines are swallowed by the root logger's WARNING default.
_shared_processors = [
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.stdlib.add_log_level,
]
structlog.configure(
    processors=[*_shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
_formatter = structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=_shared_processors,
    processors=[
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.dev.ConsoleRenderer(),
    ],
)
_handler = logging.StreamHandler()
_handler.setFormatter(_formatter)
_root = logging.getLogger()
_root.handlers = [_handler]
_root.setLevel(LOG_LEVEL)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

log = structlog.get_logger(__name__)



DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://complyagent:complyagentsecret@localhost:5432/compliance",
)
GITHUB_WEBHOOK_SECRET: str = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
GITHUB_TOKEN: str          = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO_OWNER: str     = os.environ.get("GITHUB_REPO_OWNER", "")
GITHUB_REPO_NAME: str      = os.environ.get("GITHUB_REPO_NAME", "")
QDRANT_URL: str            = os.environ.get("QDRANT_URL",  "http://localhost:6333")
REDIS_URL: str             = os.environ.get("REDIS_URL",   "redis://localhost:6379")



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise all infrastructure and start agents on startup."""
    log.info("Starting ComplyAgent API…")

    await init_db(DATABASE_URL)
    log.info("Postgres ready.")

    await init_redis(REDIS_URL)
    log.info("Redis ready.")

    await embed_controls(QDRANT_URL)
    log.info("SOC 2 controls embedded into Qdrant.")

    policy_task   = asyncio.create_task(PolicyAgent().run(),         name="policy-agent")
    cluster_task  = asyncio.create_task(ClusterOperatorAgent().run(), name="cluster-agent")
    dev_team_task = asyncio.create_task(DevTeamAgent().run(),         name="devteam-agent")
    log.info("All agents started.")

    yield   # ← app serves requests here

    log.info("Shutting down — stopping agents…")
    policy_task.cancel()
    cluster_task.cancel()
    dev_team_task.cancel()
    await close_redis()
    await close_db()



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



def _verify_github_signature(body: bytes, signature_header: str | None) -> None:
    """Validate the X-Hub-Signature-256 header from GitHub."""
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
    """Receive GitHub push and pull_request events."""
    body = await request.body()
    _verify_github_signature(body, x_hub_signature_256)

    payload: dict[str, Any] = await request.json()
    event_type = x_github_event or "unknown"

    log.info(
        "Received GitHub webhook",
        event_type=event_type,
        repo=payload.get("repository", {}).get("full_name"),
    )

    # Publish to Redis Stream — Dev Team Agent picks it up automatically
    await publish("github.prs", {
        "source":     "github",
        "event_type": event_type,
        "repo":       payload.get("repository", {}).get("full_name", ""),
        "sha":        payload.get("after", ""),
        "payload":    payload,
    })

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "received":   True,
            "event_type": event_type,
            "message":    "Event published to github.prs stream.",
        },
    )



@app.post("/webhook/prometheus", tags=["webhooks"])
async def prometheus_webhook(request: Request) -> JSONResponse:
    """Receive Alertmanager firing alerts and publish each to prometheus.alerts."""
    payload = await request.json()
    alerts = payload.get("alerts", [])
    log.info("Received %d Prometheus alert(s)", len(alerts))

    published = 0
    for alert in alerts:
        if alert.get("status") != "firing":
            continue
        labels      = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        await publish("prometheus.alerts", {
            "source":      "prometheus",
            "alertname":   labels.get("alertname", "UNKNOWN"),
            "namespace":   labels.get("namespace", "default"),
            "resource":    labels.get("pod") or labels.get("node") or labels.get("job", "unknown"),
            "labels":      labels,
            "summary":     annotations.get("summary", ""),
            "description": annotations.get("description", annotations.get("summary", "")),
            "starts_at":   alert.get("startsAt", ""),
        })
        published += 1

    log.info("Published %d firing alert(s) to prometheus.alerts stream.", published)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"received": True, "alert_count": len(alerts), "published": published},
    )



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
    repo_file_path: str | None = Field(
        default=None,
        description=(
            "Path of the file inside the GitHub repo (e.g. 'infra/main.tf'). "
            "When provided, a remediation PR is opened for every violation found."
        ),
        examples=["infra/main.tf"],
    )
    open_prs: bool = Field(
        default=False,
        description="Set to true to automatically open remediation PRs for every violation.",
    )


class FindingResponse(BaseModel):
    check_id: str
    control_id: str
    control_name: str
    resource_name: str
    file_path: str
    severity: str
    git_sha: str | None
    pr_url: str | None = None


@app.post(
    "/scan/checkov",
    response_model=list[FindingResponse],
    tags=["scanning"],
)
async def scan_checkov(req: ScanRequest) -> list[FindingResponse]:
    """Manually trigger a Checkov scan and log all violations to the evidence store."""
    path = Path(req.file_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {req.file_path}",
        )

    log.info("Running Checkov scan", file=str(path))
    findings = await run_checkov(path, git_sha=req.git_sha)

    repo_full_name = f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
    should_open_prs = (
        req.open_prs
        and req.repo_file_path
        and GITHUB_TOKEN
        and GITHUB_REPO_OWNER
        and GITHUB_REPO_NAME
    )

    responses: list[FindingResponse] = []

    async with get_session() as session:
        for finding in findings:

            control = await retrieve_by_control_id(
                finding.control_id, QDRANT_URL
            )

            explanation = await generate_explanation(
                check_id=finding.check_id,
                control_id=finding.control_id,
                control_name=finding.control_name,
                control_text=control.text,
                resource_name=finding.resource_name,
                file_path=finding.file_path,
                severity=finding.severity,
            )

            evidence_dict = finding.to_evidence_dict()
            evidence_dict["violation_description"] = (
                f"{explanation.violation_summary}\n\n"
                f"{explanation.business_impact}\n\n"
                f"Remediation: {explanation.remediation_steps}"
            )
            event = await log_event(session, evidence_dict)

            pr_url    = None
            pr_number = None

            if should_open_prs:
                try:
                    result = await open_remediation_pr(
                        github_token=GITHUB_TOKEN,
                        repo_full_name=repo_full_name,
                        file_path=req.repo_file_path,
                        check_id=finding.check_id,
                        control_id=finding.control_id,
                        control_name=finding.control_name,
                        resource_name=finding.resource_name,
                        severity=finding.severity,
                        violation_description=explanation.violation_summary,
                        control_text=control.text,
                    )
                    pr_url    = result.pr_url
                    pr_number = result.pr_number
                    await update_remediation(
                        session,
                        event.id,
                        pr_url=pr_url,
                        pr_number=pr_number,
                    )
                    log.info(
                        "Remediation PR opened",
                        check_id=finding.check_id,
                        pr=pr_url,
                    )
                except Exception as exc:
                    log.error(
                        "Failed to open PR for %s: %s",
                        finding.check_id, exc,
                    )

            responses.append(
                FindingResponse(
                    check_id=finding.check_id,
                    control_id=finding.control_id,
                    control_name=finding.control_name,
                    resource_name=finding.resource_name,
                    file_path=finding.file_path,
                    severity=finding.severity,
                    git_sha=finding.git_sha,
                    pr_url=pr_url,
                )
            )

    log.info("Checkov scan complete", violations=len(findings))
    return responses



@app.post("/dev/mock-k8s-events", tags=["dev"])
async def trigger_mock_k8s_events(count: int = 3) -> dict:
    """Publish mock Kubernetes drift events to the k8s.events Redis Stream."""
    from scanners.k8s_watcher import publish_mock_events
    msg_ids = await publish_mock_events(count=count, delay_seconds=0)
    return {
        "published": len(msg_ids),
        "stream":    "k8s.events",
        "msg_ids":   msg_ids,
    }


@app.post("/dev/mock-tf-plan", tags=["dev"])
async def trigger_mock_tf_plan(
    file_path: str = "tests/fixtures/demo.tf",
    repo_file_path: str = "infra/main.tf",
) -> dict:
    """Publish a Terraform plan event to the tf.plans Redis Stream."""
    msg_id = await publish("tf.plans", {
        "source":         "manual",
        "file_path":      file_path,
        "repo_file_path": repo_file_path,
        "git_sha":        "",
    })
    return {"published": 1, "stream": "tf.plans", "msg_id": msg_id}



@app.get("/evidence", tags=["evidence"])
async def list_evidence(limit: int = 50) -> list[dict]:
    """Return the `limit` most recent evidence events."""
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
