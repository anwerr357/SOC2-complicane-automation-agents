# ComplyAgent — Developer Documentation

> Three autonomous agents. One remediation loop. Full SOC 2 audit trail.
> Jump to a module: [checkov_runner](checkov_runner.md) · [evidence_store](evidence_store.md) · [webhooks](webhooks.md) · [agents](agents/) · [remediation loop](remediation_loop.md)

---

## Full system data flow

```
  GitHub / CI / K8s             FastAPI                  Redis Streams
  ─────────────────             ───────                  ─────────────

  POST /webhook/github  ──►  receive_github_webhook()
  POST /scan/checkov    ──►  scan_checkov()
  K8s watch event       ──►  (k8s_watcher publishes)  ──►  k8s.events
                                                       ──►  tf.plans
                                                       ──►  github.prs
                                                             │
                                          ┌──────────────────┤
                                          │                  │
                                    Policy Agent      Dev Team Agent
                                    Checkov scan      Trufflehog + Semgrep
                                          │                  │
                                   Cluster Operator          │
                                   k8s drift detect          │
                                          │                  │
                                          └──────┬───────────┘
                                                 ▼
                                        run_remediation_loop()
                                        ┌─────────────────────┐
                                        │ 1. NOTIFY  (Postgres)│
                                        │ 2. LEARN   (Qdrant)  │
                                        │ 3. RECOMMEND (Claude)│
                                        │ 4. MUTATE  (GitHub)  │
                                        │ 5. VALIDATE (re-scan)│
                                        └──────────┬──────────┘
                                                   │
                                        ┌──────────┴──────────┐
                                        │                     │
                                   GitHub PR             Slack alert
                                   (compliance-fix/*)    (on FAIL)
```

---

## Module map

| File | Responsibility | Public surface |
|------|---------------|----------------|
| [scanners/checkov_runner.py](checkov_runner.md) | Async Checkov subprocess wrapper; maps check IDs → SOC 2 controls | `CheckovRunner`, `CheckovFinding`, `run_checkov()`, `SOC2_CONTROL_MAP` |
| [store/models.py](evidence_store.md#models) | SQLAlchemy ORM — `evidence_events` table | `EvidenceEvent`, `AgentName`, `ScannerUsed`, `Severity`, `EventStatus` |
| [store/evidence.py](evidence_store.md#evidence) | Async DB helper layer | `init_db()`, `log_event()`, `update_remediation()`, `escalate_event()`, `get_open_events()`, `get_recent_events()` |
| [api/webhooks.py](webhooks.md) | FastAPI app — webhook receivers, scan trigger, evidence read API | `POST /scan/checkov`, `GET /evidence`, `POST /webhook/github`, `/healthz` |
| [agents/policy_agent.py](agents/policy_agent.md) | Terraform + K8s governance via Checkov | `PolicyAgent` |
| [agents/cluster_operator.py](agents/cluster_operator.md) | Live K8s + Prometheus drift detection | `ClusterOperatorAgent` |
| [agents/dev_team_agent.py](agents/dev_team_agent.md) | PR scanning via Trufflehog + Semgrep | `DevTeamAgent` |
| [agents/remediation.py](remediation_loop.md) | Shared 5-step remediation loop | `run_remediation_loop()`, `LoopOutcome` |
| `brain/llm.py` | Claude API client — structured explanation output | `generate_explanation()` |
| `brain/rag.py` | Qdrant retrieval — SOC 2 control text by control ID | `retrieve_by_control_id()` |
| `mutate/mutate.py` | GitHub branch + commit + PR creation | `open_remediation_pr()` |
| `mutate/validate.py` | Post-remediation re-scan | `validate_remediation()` |
| `notify/slack.py` | Slack escalation notifications | `post_escalation()`, `post_remediation()` |

---

## Cross-cutting conventions

### Async throughout
Every function touching I/O is `async`. Checkov uses `asyncio.create_subprocess_exec`. DB uses SQLAlchemy 2.0 asyncio mode with `asyncpg`.

### Structured finding shape
`CheckovFinding.to_evidence_dict()` is the canonical contract between scanners and the store. Adding a new scanner means implementing an equivalent `to_evidence_dict()` — no changes to the store or API.

### Immutable audit trail
`evidence_events` rows are never deleted. `status` progresses forward (`open → remediated | escalated | false_positive`) and is never reset. Raw scanner JSON is kept verbatim in `raw_finding` JSONB.

### Error handling philosophy
- Scanner failures return `[]` and log a warning — never crash the API
- DB failures bubble up and roll back automatically via `get_session()`
- Unknown Checkov check IDs map to `CC0.0` — new rules never break the pipeline

---

## Environment variables

| Variable | Used by | Default |
|----------|---------|---------|
| `DATABASE_URL` | `store/evidence.py` | `postgresql+asyncpg://complyagent:complyagentsecret@localhost:5432/compliance` |
| `REDIS_URL` | `agents/base_agent.py` | `redis://localhost:6379` |
| `ANTHROPIC_API_KEY` | `brain/llm.py` | — |
| `QDRANT_URL` | `brain/rag.py` | `http://localhost:6333` |
| `GITHUB_TOKEN` | `mutate/mutate.py`, `agents/dev_team_agent.py` | — |
| `GITHUB_REPO_OWNER` | `agents/policy_agent.py` | — |
| `GITHUB_REPO_NAME` | `agents/policy_agent.py` | — |
| `GITHUB_WEBHOOK_SECRET` | `api/webhooks.py` | `""` |
| `SLACK_BOT_TOKEN` | `notify/slack.py` | — |
| `SLACK_ALERT_CHANNEL` | `notify/slack.py` | `#compliance-alerts` |
