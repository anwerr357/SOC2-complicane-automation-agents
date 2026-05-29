# `api/webhooks.py` — FastAPI Application

The single HTTP entry point for all inbound events.  Receives webhooks from
GitHub and Prometheus, exposes a manual scan trigger for development and CI,
and serves the evidence read API used by the React dashboard.

---

## Startup sequence

The FastAPI `lifespan` context manager runs on every process start:

```
uvicorn starts
    │
    └── lifespan(app) enters
            │
            ├── await init_db(DATABASE_URL)
            │       creates AsyncEngine (asyncpg)
            │       runs CREATE TABLE IF NOT EXISTS
            │
            ├── [Week 4] Redis consumer group creation
            │
            └── yield  ← app begins serving requests
                │
                (process runs…)
                │
            ── lifespan exits ──
                │
                └── await close_db()
                        disposes connection pool
```

---

## Configuration

Read from environment variables at module load time:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://soc2:soc2secret@localhost:5432/compliance` | Asyncpg connection string passed to `init_db()` |
| `GITHUB_WEBHOOK_SECRET` | `""` | HMAC secret shared with GitHub.  If empty, signature verification is skipped with a warning (for local dev). |

---

## Endpoints

### `GET /healthz` — Liveness probe

```
GET /healthz
→ 200 { "status": "alive" }
```

Always returns `200` if the process is running.  Used by Docker's
`HEALTHCHECK` and Kubernetes liveness probes.  Does **not** check DB
connectivity — that is the job of `/readyz`.

---

### `GET /readyz` — Readiness probe

```
GET /readyz
→ 200 { "status": "ready" }
→ 503 { "detail": "Database not ready: <error>" }
```

Executes `SELECT 1` against Postgres.  Returns `503` if the connection fails.
Kubernetes uses this to hold traffic until the DB is reachable at startup.

---

### `POST /webhook/github` — GitHub events

```
POST /webhook/github
Headers:
    X-GitHub-Event:      push | pull_request | ...
    X-Hub-Signature-256: sha256=<hmac>
Body: GitHub webhook JSON payload
→ 202 { "received": true, "event_type": "push", "message": "Event queued for processing." }
→ 401 if signature mismatch
```

#### Signature verification

GitHub signs every webhook delivery with `HMAC-SHA256` using the shared
secret configured in the repo's webhook settings.  The header is
`X-Hub-Signature-256: sha256=<hex>`.

Verification logic (`_verify_github_signature`):

1. If `GITHUB_WEBHOOK_SECRET` is not set → log a warning, skip check
   (safe for local development, never do this in production).
2. If the header is missing or malformed → `HTTP 401`.
3. Compute `HMAC-SHA256(secret, request_body)` and compare with
   `hmac.compare_digest()` to prevent timing attacks.
4. If mismatch → `HTTP 401`.

**Week 1:** Acknowledges the event and returns `202`.  
**Week 2:** Publishes to the `github.prs` Redis Stream for Dev Team Agent.

---

### `POST /webhook/prometheus` — Alertmanager events

```
POST /webhook/prometheus
Body: Alertmanager JSON payload (alerts array)
→ 202 { "received": true, "alert_count": 3 }
```

Receives Prometheus Alertmanager webhooks.  Maps alert labels to SOC 2
controls and publishes to `prometheus.alerts` Redis Stream.

**Week 1:** Parses and acknowledges.  
**Week 4:** Full Redis Stream publish + Cluster Operator integration.

---

### `POST /scan/checkov` — Manual scan trigger ⭐ (Week 1 — fully implemented)

```
POST /scan/checkov
Content-Type: application/json

{
    "file_path": "tests/fixtures/demo.tf",
    "git_sha":   "abc123def456"           ← optional
}

→ 200 [
    {
        "check_id":     "CKV2_AWS_61",
        "control_id":   "CC6.7",
        "control_name": "Encryption at rest",
        "resource_name": "aws_s3_bucket.app_data",
        "file_path":    "/abs/path/tests/fixtures/demo.tf",
        "severity":     "MEDIUM",
        "git_sha":      "abc123def456"
    },
    ...
]

→ 404 if file_path does not exist on disk
```

#### Request schema — `ScanRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | `str` | ✓ | Path to a `.tf` or `.yaml` file.  Can be absolute or relative to the process working directory. |
| `git_sha` | `str \| null` | — | HEAD commit SHA.  Attached to every evidence row for audit attribution. |

#### Response schema — `FindingResponse[]`

| Field | Type | Description |
|-------|------|-------------|
| `check_id` | `str` | Checkov check identifier (e.g. `CKV2_AWS_61`) |
| `control_id` | `str` | SOC 2 control (e.g. `CC6.7`) |
| `control_name` | `str` | Human-readable control label |
| `resource_name` | `str` | Terraform resource or K8s object name |
| `file_path` | `str` | Absolute path of the scanned file |
| `severity` | `str` | `HIGH \| MEDIUM \| LOW \| INFO` |
| `git_sha` | `str \| null` | SHA passed in the request |

#### Internal sequence

```
scan_checkov(req)
    │
    ├── Path(req.file_path).exists()  →  404 if missing
    │
    ├── await run_checkov(path, git_sha=req.git_sha)
    │       spawns checkov subprocess
    │       returns list[CheckovFinding]
    │
    ├── async with get_session() as session:
    │       for finding in findings:
    │           await log_event(session, finding.to_evidence_dict())
    │       # session.commit() on context exit
    │
    └── return [FindingResponse(...) for f in findings]
```

**Side effect:** every finding is written to `evidence_events` before the
response is returned.  If zero violations are found, the endpoint returns `[]`
(not `404`) — an empty scan result is itself meaningful evidence.

#### curl example

```bash
# Scan the seeded demo fixture
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "tests/fixtures/demo.tf", "git_sha": "abc123"}'

# Scan a real Terraform file
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/workspace/infra/main.tf"}'
```

---

### `GET /evidence` — Recent evidence events

```
GET /evidence?limit=50

→ 200 [
    {
        "id":                    "uuid",
        "created_at":            "2026-05-27T10:00:00+00:00",
        "agent_name":            "policy",
        "scanner_used":          "checkov",
        "check_id":              "CKV2_AWS_61",
        "control_id":            "CC6.7",
        "control_name":          "Encryption at rest",
        "resource_name":         "aws_s3_bucket.app_data",
        "file_path":             "infra/main.tf",
        "severity":              "MEDIUM",
        "status":                "open",
        "pr_url":                null,
        "violation_description": ""
    },
    ...
]
```

| Query param | Type | Default | Description |
|-------------|------|---------|-------------|
| `limit` | `int` | `50` | Maximum number of events to return, ordered newest-first |

Used by the React dashboard event feed (Week 6).

---

### `GET /evidence/{control_id}` — Events by control

```
GET /evidence/CC6.7

→ 200 [
    {
        "id":            "uuid",
        "created_at":    "2026-05-27T10:00:00+00:00",
        "check_id":      "CKV2_AWS_61",
        "control_id":    "CC6.7",
        "resource_name": "aws_s3_bucket.app_data",
        "file_path":     "infra/main.tf",
        "severity":      "MEDIUM",
        "status":        "open",
        "pr_url":        null
    },
    ...
]
```

| Path param | Description |
|------------|-------------|
| `control_id` | SOC 2 criterion ID, e.g. `CC6.7`, `A1.1`, `CC7.2` |

Returns all events for that control across all statuses, ordered newest-first.
Used by the per-control drill-down panel in the dashboard.

---

## Logging

Structured logging via [structlog](https://www.structlog.org/) is configured
at module load time:

```python
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    ...
)
```

Every log call uses keyword arguments for machine-parseable output:

```python
log.info("Received GitHub webhook", event_type="push", repo="org/repo")
log.info("Running Checkov scan", file="infra/main.tf")
log.info("Checkov scan complete", violations=12)
log.error("Readiness check failed", error="connection refused")
```

In production, swap `ConsoleRenderer` for `JSONRenderer` to emit structured
JSON logs that can be ingested by Datadog, Splunk, or CloudWatch.

---

## Interactive API docs

FastAPI auto-generates OpenAPI documentation:

| URL | Description |
|-----|-------------|
| `http://localhost:8000/docs` | Swagger UI — try endpoints in the browser |
| `http://localhost:8000/redoc` | ReDoc — cleaner read-only reference |
| `http://localhost:8000/openapi.json` | Raw OpenAPI 3.1 spec |

---

## CORS

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Permissive for local development.  Before production deployment, restrict
`allow_origins` to the React dashboard's domain.

---

## Future endpoints (planned)

| Endpoint | Week | Description |
|----------|------|-------------|
| `POST /webhook/github` (full) | 2 | Publish to Redis Stream `github.prs` |
| `GET /evidence/stats` | 6 | Compliance score per control (for dashboard gauge) |
| `GET /evidence/trend` | 6 | Violation count over time (for Recharts line chart) |
| `POST /webhook/prometheus` (full) | 4 | Forward to Redis Stream `prometheus.alerts` |
