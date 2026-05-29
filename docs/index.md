# SOC 2 Compliance Agent — Developer Documentation

> **Week 1 implementation.** Four modules are fully built and tested.
> Subsequent weeks add the remaining stubs. Jump straight to a module:
> [checkov_runner](checkov_runner.md) · [evidence_store](evidence_store.md) · [webhooks](webhooks.md)

---

## End-to-end data flow (Week 1)

```
  Engineer / CI                  FastAPI                CheckovRunner         Postgres
  ─────────────                  ───────                ─────────────         ────────

  POST /scan/checkov
  { file_path, git_sha }  ──►  scan_checkov()
                                  │
                                  │  await run_checkov(path, git_sha)
                                  ├──────────────────────────────►
                                  │                        asyncio.create_subprocess_exec(
                                  │                          "checkov --file path
                                  │                                   --output json
                                  │                                   --quiet --compact"
                                  │                        )
                                  │                                │
                                  │                        parse stdout JSON
                                  │                        map check_id → control_id
                                  │                        build CheckovFinding[]
                                  │◄──────────────────────────────┤
                                  │
                                  │  async with get_session():
                                  │    for finding in findings:
                                  │      await log_event(session, finding.to_evidence_dict())
                                  ├───────────────────────────────────────────►
                                  │                                INSERT INTO
                                  │                                evidence_events ...
                                  │◄───────────────────────────────────────────
                                  │
  HTTP 200                        │
  [{ check_id, control_id, ... }] │
  ◄───────────────────────────────┘
```

---

## Module map

| File | Responsibility | Public surface |
|------|---------------|----------------|
| [scanners/checkov_runner.py](checkov_runner.md) | Async Checkov subprocess wrapper; maps check IDs → SOC 2 controls | `CheckovRunner`, `CheckovFinding`, `run_checkov()`, `SOC2_CONTROL_MAP` |
| [store/models.py](evidence_store.md#models) | SQLAlchemy ORM — `evidence_events` table + enumerations | `EvidenceEvent`, `AgentName`, `ScannerUsed`, `Severity`, `EventStatus` |
| [store/evidence.py](evidence_store.md#evidence) | Async DB helper layer; all reads and writes go through here | `init_db()`, `close_db()`, `get_session()`, `log_event()`, `update_remediation()`, `escalate_event()`, `get_open_events()`, `get_recent_events()`, `get_events_by_control()` |
| [api/webhooks.py](webhooks.md) | FastAPI app — webhook receivers, scan trigger, evidence read API | `POST /scan/checkov`, `GET /evidence`, `POST /webhook/github`, `/healthz`, `/readyz` |

---

## Cross-cutting conventions

### Async throughout
Every function that touches I/O is `async`.  The Checkov subprocess uses
`asyncio.create_subprocess_exec` so it never blocks the event loop.
The DB layer uses SQLAlchemy 2.0 asyncio mode with `asyncpg` as the driver.

### Structured finding shape
`CheckovFinding.to_evidence_dict()` is the **one canonical contract** between
the scanner and the store.  It returns exactly the keys that `log_event()`
expects.  Adding a new scanner means implementing the same `to_evidence_dict()`
method on a new dataclass — no changes needed to the store or API.

### Immutable audit trail
`evidence_events` rows are never deleted.  `status` progresses forward
(`open → remediated | escalated | false_positive`) but is never reset.
Every raw scanner JSON blob is kept verbatim in the `raw_finding` JSONB column.

### Error handling philosophy
- Scanner failures (non-zero exit code, bad JSON) return `[]` and log a
  warning — they never crash the API.
- DB failures bubble up as exceptions and roll back the transaction
  automatically via `get_session()`.
- Unknown Checkov check IDs are mapped to `CC0.0 / Unknown control` — new
  Checkov rules never break the pipeline; they just need a follow-up mapping.

---

## Environment variables

| Variable | Used by | Default |
|----------|---------|---------|
| `DATABASE_URL` | `api/webhooks.py`, `store/evidence.py` | `postgresql+asyncpg://soc2:soc2secret@localhost:5432/compliance` |
| `GITHUB_WEBHOOK_SECRET` | `api/webhooks.py` | `""` (signature check skipped if unset) |
| `ANTHROPIC_API_KEY` | `brain/llm.py` (Week 3) | — |
| `REDIS_URL` | agents (Week 4) | `redis://localhost:6379` |
| `QDRANT_URL` | `brain/rag.py` (Week 3) | `http://localhost:6333` |
