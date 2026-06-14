# `store/` — Evidence Store

The evidence store is the audit trail that SOC 2 auditors actually inspect.
It consists of two files with distinct responsibilities:

| File | Job |
|------|-----|
| [store/models.py](#models) | ORM model + enumerations — defines the DB schema |
| [store/evidence.py](#evidence) | Async helper functions — all reads and writes |

---

<a name="models"></a>
## `store/models.py` — ORM models

### Design principles

**Immutable audit log** — rows are never deleted.  Once a violation is
recorded it exists permanently.  Only the `status` column advances forward
(`open → remediated | escalated | false_positive`).  This is a deliberate
audit-trail guarantee: every IaC change ever scanned has a timestamped,
permanent record.

**Verbatim raw payload** — the `raw_finding` JSONB column stores the full
scanner JSON as-is.  If the normalisation logic has a bug, the raw data is
always available for re-processing.

**Enum types in Postgres** — `agent_name`, `scanner_used`, `severity`, and
`status` are native Postgres `ENUM` types (not plain strings).  This enforces
data integrity at the DB level and gives the dashboard stable values to filter on.

---

### Enumerations

#### `AgentName`

```python
class AgentName(str, PyEnum):
    POLICY           = "policy"
    CLUSTER_OPERATOR = "cluster_operator"
    DEV_TEAM         = "dev_team"
    MANUAL           = "manual"
```

Which agent produced this evidence event.  `MANUAL` is used for events
triggered via the `/scan/checkov` API rather than an autonomous agent loop.

#### `ScannerUsed`

```python
class ScannerUsed(str, PyEnum):
    CHECKOV    = "checkov"
    TRUFFLEHOG = "trufflehog"
    SEMGREP    = "semgrep"
    K8S_WATCH  = "k8s_watch"
    MANUAL     = "manual"
```

Which scanner produced the finding.  Allows dashboard queries like
"all Trufflehog-detected secrets this week".

#### `Severity`

```python
class Severity(str, PyEnum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"
    INFO   = "INFO"
```

Normalised from the scanner's native severity labels via `SEVERITY_MAP` in
the scanner layer before the event reaches the store.

#### `EventStatus`

```python
class EventStatus(str, PyEnum):
    OPEN           = "open"
    REMEDIATED     = "remediated"
    ESCALATED      = "escalated"
    FALSE_POSITIVE = "false_positive"
```

The lifecycle state of a violation:

```
     ┌──────────┐
     │   OPEN   │  ← initial state on INSERT
     └────┬─────┘
          │
    ┌─────┴──────────────────┐
    │                        │
    ▼                        ▼
┌────────────┐     ┌──────────────────┐
│ REMEDIATED │     │    ESCALATED     │
│ (PR merged)│     │ (max retries or  │
└────────────┘     │  human decision) │
                   └──────────────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  FALSE_POSITIVE  │
                   │  (manual review) │
                   └──────────────────┘
```

---

### `class EvidenceEvent`

```python
class EvidenceEvent(Base):
    __tablename__ = "evidence_events"
```

One row per compliance violation, regardless of status.

#### Full schema

| Column | Type | Nullable | Index | Description |
|--------|------|----------|-------|-------------|
| `id` | `UUID` | No | PK | Auto-generated UUID (server default `gen_random_uuid()`) |
| `created_at` | `TIMESTAMPTZ` | No | — | UTC timestamp; set once on INSERT, never updated |
| `agent_name` | `ENUM` | No | ✓ | `AgentName` — which agent produced this event |
| `scanner_used` | `ENUM` | No | ✓ | `ScannerUsed` — which scanner found the violation |
| `check_id` | `VARCHAR(64)` | No | ✓ | Scanner-native check identifier (e.g. `CKV2_AWS_61`) |
| `control_id` | `VARCHAR(32)` | No | ✓ | SOC 2 Trust Service Criterion (e.g. `CC6.7`) |
| `control_name` | `VARCHAR(256)` | No | — | Human-readable control label (e.g. `Encryption at rest`) |
| `resource_name` | `VARCHAR(512)` | No | — | Terraform resource / K8s object / filename that violated |
| `file_path` | `TEXT` | No | — | Relative path to the violating file in the repo |
| `git_sha` | `VARCHAR(64)` | Yes | — | HEAD SHA at scan time (null for live K8s drift events) |
| `severity` | `ENUM` | No | ✓ | `Severity` — normalised severity |
| `violation_description` | `TEXT` | No | — | LLM-generated plain-English summary (empty until Week 3) |
| `raw_finding` | `JSONB` | No | — | Verbatim scanner JSON — never discarded |
| `pr_url` | `TEXT` | Yes | — | GitHub PR URL once remediation PR is opened |
| `pr_number` | `INTEGER` | Yes | — | GitHub PR number (for easy linking) |
| `status` | `ENUM` | No | ✓ | `EventStatus` — lifecycle state |
| `remediation_run` | `INTEGER` | No | — | Counter: how many remediation attempts have run |

#### Indexes

Columns with `✓` in the Index column above have individual B-tree indexes.
This supports the dashboard's most common queries:
- Filter by `control_id` (compliance score per criterion)
- Filter by `status = 'open'` (open violations panel)
- Filter by `severity` (HIGH priority queue)
- Filter by `agent_name` or `scanner_used` (per-agent analytics)

#### `__repr__`

```python
>>> event
<EvidenceEvent id=a1b2c3d4 control=CC6.7 check=CKV2_AWS_61 status=open>
```

---

<a name="evidence"></a>
## `store/evidence.py` — Async helper layer

All database I/O in the system goes through this module.  No agent, scanner,
or API handler issues raw SQL or touches SQLAlchemy directly — everything uses
these functions.

---

### Module state

Two module-level variables are set by `init_db()` and used by all helpers:

```python
_engine: AsyncEngine | None           # asyncpg connection pool
_session_factory: async_sessionmaker  # factory for AsyncSession instances
```

---

### Lifecycle functions

#### `init_db(database_url)`

```python
async def init_db(database_url: str) -> None
```

Must be called **once at startup**, before any other function in this module.

1. Creates the `AsyncEngine` with `asyncpg` driver.
2. Runs `CREATE TABLE IF NOT EXISTS` for every ORM model (fast path for
   development and CI; use Alembic migrations for production schema changes).
3. Sets `_engine` and `_session_factory` for subsequent calls.

| Parameter | Description |
|-----------|-------------|
| `database_url` | Full asyncpg connection URL, e.g. `postgresql+asyncpg://complyagent:secret@localhost:5432/compliance` |

Connection pool settings:

| Setting | Value | Reason |
|---------|-------|--------|
| `pool_size` | 10 | One connection per concurrent agent/request |
| `max_overflow` | 20 | Burst headroom during scan spikes |
| `pool_pre_ping` | `True` | Automatically drops stale connections after DB restart |
| `expire_on_commit` | `False` | ORM objects remain usable after `session.commit()` |

#### `close_db()`

```python
async def close_db() -> None
```

Disposes the engine and closes all pooled connections.  Called from the
FastAPI `lifespan` shutdown handler.

#### `get_session()`

```python
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]
```

Async context manager that yields a transactional `AsyncSession`.

- On success: calls `session.commit()` before exiting.
- On exception: calls `session.rollback()` and re-raises.

```python
# FastAPI handler usage
async with get_session() as session:
    await log_event(session, finding.to_evidence_dict())

# Agent usage
async with get_session() as session:
    events = await get_open_events(session)
```

**Raises `RuntimeError`** if called before `init_db()`.

---

### Write functions

#### `log_event(session, finding) → EvidenceEvent`

```python
async def log_event(
    session: AsyncSession,
    finding: dict,
) -> EvidenceEvent
```

Persists a scanner finding as a new `evidence_events` row.

**Required keys in `finding`:**

| Key | Type | Description |
|-----|------|-------------|
| `agent_name` | `str` | `AgentName` value |
| `scanner_used` | `str` | `ScannerUsed` value |
| `check_id` | `str` | Scanner-native ID (e.g. `CKV2_AWS_61`) |
| `control_id` | `str` | SOC 2 criterion (e.g. `CC6.7`) |
| `control_name` | `str` | Human label |
| `resource_name` | `str` | Violating resource |
| `file_path` | `str` | File path |
| `severity` | `str` | `Severity` value |
| `raw_finding` | `dict` | Full scanner JSON |

**Optional keys:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `git_sha` | `str` | `None` | Commit SHA |
| `violation_description` | `str` | `""` | LLM description (Week 3) |

Uses `session.flush()` (not `commit()`) so the caller can batch multiple
`log_event()` calls in one transaction.

Returns the created `EvidenceEvent` with the DB-assigned `id` populated.

#### `update_remediation(session, event_id, *, pr_url, pr_number, status)`

```python
async def update_remediation(
    session: AsyncSession,
    event_id: UUID,
    *,
    pr_url: str,
    pr_number: int,
    status: EventStatus = EventStatus.REMEDIATED,
) -> None
```

Called by `mutate/mutate.py` after a GitHub PR is opened.  Attaches the PR
URL and number, and advances the event status.

| Parameter | Description |
|-----------|-------------|
| `event_id` | UUID of the event to update |
| `pr_url` | Full GitHub PR URL (e.g. `https://github.com/org/repo/pull/42`) |
| `pr_number` | GitHub PR number for linking |
| `status` | Defaults to `REMEDIATED`; pass `ESCALATED` if the PR is created as an escalation notice |

#### `escalate_event(session, event_id)`

```python
async def escalate_event(session: AsyncSession, event_id: UUID) -> None
```

Marks an event as `ESCALATED` — used when the remediation loop has exhausted
its retry budget or the post-remediation validation scan still fails.  A Slack
alert is sent separately by the agent.

#### `increment_remediation_run(session, event_id)`

```python
async def increment_remediation_run(
    session: AsyncSession, event_id: UUID
) -> None
```

Increments `remediation_run` by 1 on each pass through the remediation loop.
The agent uses this counter to decide when to escalate (`remediation_run >= 3`).

---

### Read functions

#### `get_open_events(session) → list[EvidenceEvent]`

```python
async def get_open_events(session: AsyncSession) -> list[EvidenceEvent]
```

Returns all events with `status = 'open'`, ordered newest-first.
Used by agents to find violations that still need remediation on restart.

#### `get_events_by_control(session, control_id) → list[EvidenceEvent]`

```python
async def get_events_by_control(
    session: AsyncSession,
    control_id: str,
) -> list[EvidenceEvent]
```

All events (any status) for a single SOC 2 criterion.  Powers the
`GET /evidence/{control_id}` API endpoint and the per-control panel in the
React dashboard.

#### `get_recent_events(session, limit=50) → list[EvidenceEvent]`

```python
async def get_recent_events(
    session: AsyncSession,
    limit: int = 50,
) -> list[EvidenceEvent]
```

The `limit` most recent events across all controls and statuses.
Powers the main `GET /evidence` endpoint and the dashboard event feed.

---

## Usage examples

### Full scan-and-log pipeline

```python
from scanners.checkov_runner import run_checkov
from store.evidence import init_db, get_session, log_event

await init_db("postgresql+asyncpg://complyagent:secret@localhost:5432/compliance")

findings = await run_checkov("infra/main.tf", git_sha="abc123")

async with get_session() as session:
    for finding in findings:
        event = await log_event(session, finding.to_evidence_dict())
        print(f"Logged event {event.id} — {event.control_id}")
```

### Query open violations

```python
async with get_session() as session:
    events = await get_open_events(session)

for e in events:
    print(f"{e.created_at}  {e.control_id}  {e.resource_name}  {e.severity}")
```

### Attach a remediation PR

```python
from store.evidence import get_session, update_remediation
from store.models import EventStatus

async with get_session() as session:
    await update_remediation(
        session,
        event_id=uuid.UUID("a1b2c3d4-..."),
        pr_url="https://github.com/org/repo/pull/42",
        pr_number=42,
        status=EventStatus.REMEDIATED,
    )
```

---

## Raw SQL equivalent (for auditors)

The full evidence table in SQL — useful when connecting BI tools like Metabase
or Redash directly to the Postgres instance:

```sql
SELECT
    id,
    created_at,
    agent_name,
    scanner_used,
    check_id,
    control_id,
    control_name,
    resource_name,
    file_path,
    git_sha,
    severity,
    violation_description,
    status,
    pr_url,
    pr_number,
    remediation_run
FROM evidence_events
ORDER BY created_at DESC;

-- All open HIGH-severity violations
SELECT * FROM evidence_events
WHERE status = 'open' AND severity = 'HIGH'
ORDER BY created_at DESC;

-- Compliance score per control (% remediated)
SELECT
    control_id,
    COUNT(*) FILTER (WHERE status = 'remediated') AS remediated,
    COUNT(*) AS total,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'remediated') / COUNT(*), 1
    ) AS pct_remediated
FROM evidence_events
GROUP BY control_id
ORDER BY control_id;
```
