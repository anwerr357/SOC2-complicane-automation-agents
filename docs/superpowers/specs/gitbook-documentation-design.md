# GitBook Documentation — Design Spec

**Date:** 2026-06-14
**Author:** anwer
**Status:** Approved

---

## Goal

Create a GitBook documentation site for ComplyAgent, synced from the GitHub repo. Covers both operators (evaluating/running the system) and contributors (onboarding to extend it). Six top-level pages with agent sub-pages nested under "How to Use".

---

## Approach

**Approach A — Flat six-page structure with sub-pages under "How to Use".**

GitBook GitHub sync enabled: markdown files live in `docs/gitbook/`, `SUMMARY.md` defines navigation, changes pushed to GitHub automatically update GitBook.

---

## File Layout

```
docs/gitbook/
├── SUMMARY.md                        ← GitBook navigation tree
├── introduction.md
├── installation.md
├── quick-start.md
├── how-to-use/
│   ├── README.md                     ← section overview page
│   ├── policy-agent.md
│   ├── cluster-operator-agent.md
│   ├── dev-team-agent.md
│   └── remediation-loop.md
├── configuration.md
└── troubleshooting.md
```

---

## SUMMARY.md Structure

```markdown
# ComplyAgent

* [Introduction](introduction.md)
* [Installation](installation.md)
* [Quick Start](quick-start.md)
* [How to Use](how-to-use/README.md)
  * [Policy Agent](how-to-use/policy-agent.md)
  * [Cluster Operator Agent](how-to-use/cluster-operator-agent.md)
  * [Dev Team Agent](how-to-use/dev-team-agent.md)
  * [Remediation Loop](how-to-use/remediation-loop.md)
* [Configuration](configuration.md)
* [Troubleshooting](troubleshooting.md)
```

---

## Page Content Specs

### `introduction.md`
**Audience:** Both

- What ComplyAgent does (1-paragraph hook)
- Problem it solves: compliance as a quarterly audit vs. continuous automation
- Architecture diagram (ASCII — same as README)
- SOC 2 control coverage table (CC6.1 → A1.1)
- Tech stack summary table
- Link to Installation to get started

---

### `installation.md`
**Audience:** Both

- Prerequisites: Docker + Docker Compose v2, Python 3.12 (local dev only), `checkov`
- Step 1: Clone the repo
- Step 2: Copy `.env.example` → `.env`, fill in required vars (ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET)
- Step 3: `docker compose up --build`
- Services started and their ports:
  - FastAPI: http://localhost:8000
  - API docs: http://localhost:8000/docs
  - Qdrant dashboard: http://localhost:6333/dashboard
  - Redis: localhost:6379
  - Postgres: localhost:5432
  - Dashboard: http://localhost:5173
- Verify installation: `curl http://localhost:8000/healthz`

---

### `quick-start.md`
**Audience:** Operator

Goal: running first scan and seeing results in under 5 minutes.

- Step 1: Start the stack (`docker compose up --build`)
- Step 2: Trigger a Checkov scan on the demo fixture
  ```bash
  curl -X POST http://localhost:8000/scan/checkov \
    -H "Content-Type: application/json" \
    -d '{"file_path": "tests/fixtures/demo.tf", "git_sha": "abc123"}'
  ```
- Step 3: View findings
  ```bash
  curl http://localhost:8000/evidence
  curl http://localhost:8000/evidence/CC6.7
  ```
- Step 4: Simulate a GitHub PR webhook to trigger the Dev Team Agent
  ```bash
  curl -X POST http://localhost:8000/webhook/github \
    -H "Content-Type: application/json" \
    -H "X-GitHub-Event: pull_request" \
    -d '{"action": "opened", "pull_request": {"number": 42, "head": {"sha": "abc123", "repo": {"full_name": "org/repo"}}}}'
  ```
- What to expect: scan → brain lookup → Claude explanation → remediation PR opened on GitHub
- Link to "How to Use" for deeper detail

---

### `how-to-use/README.md`
**Audience:** Both

- Overview: three agents watch different surfaces; all feed the same remediation loop
- Table: Agent | Watches | Triggers | SOC 2 controls covered
- Two modes of operation:
  - **Event-driven** (production): Redis Streams receive events from GitHub webhooks, Terraform CI, and the Kubernetes watcher automatically
  - **Manual** (development/testing): `POST /scan/checkov` and `POST /webhook/github` endpoints
- Links to the four sub-pages

---

### `how-to-use/policy-agent.md`
**Audience:** Contributor

- Purpose: Terraform + Kubernetes governance via Checkov
- Redis streams consumed: `tf.plans`, `k8s.events`
- LangGraph state machine steps: `scan → map_to_control → brain_lookup → recommend → mutate`
- Example end-to-end:
  - S3 bucket in `infra/main.tf` missing `server_side_encryption_configuration`
  - → `CKV2_AWS_61` → CC6.7
  - → Claude generates explanation + fix
  - → PR opened: `compliance-fix/CC6.7/CKV2_AWS_61`
- How to extend: add a line to `SOC2_CONTROL_MAP` in `scanners/checkov_runner.py`

---

### `how-to-use/cluster-operator-agent.md`
**Audience:** Contributor

- Purpose: live Kubernetes drift detection via `kubernetes-asyncio` watch API
- Redis streams consumed: `k8s.events`
- What it catches that Checkov misses: live runtime state that bypasses GitOps (e.g. direct `kubectl edit`)
- LangGraph steps: `watch_event → detect_drift → brain_lookup → recommend → mutate`
- Example end-to-end:
  - Direct `kubectl edit deployment/api` adds a `hostPath` volume mount
  - → CC6.6 violation
  - → Slack alert + PR to remove the mount from the Helm values file
- Drift detection logic: compares live cluster state to last known Git state

---

### `how-to-use/dev-team-agent.md`
**Audience:** Contributor

- Purpose: PR-level secret detection and SAST scanning
- Redis streams consumed: `github.prs`
- Scanner chain:
  1. Trufflehog: scans full git history of the PR branch for live secrets
  2. Semgrep: runs custom rules from `semgrep_rules/` for code-level compliance patterns
- Example end-to-end:
  - New `/api/users` POST endpoint writes to DB but never calls `audit_log()`
  - → Semgrep custom rule fires → CC7.2 violation
  - → PR comment added + remediation PR opened with missing `audit_log()` call
- How to extend: add a `.yaml` rule file to `semgrep_rules/`

---

### `how-to-use/remediation-loop.md`
**Audience:** Both

- The 5-step loop every agent runs on every violation:
  1. **NOTIFY** — publish violation event to Redis Streams
  2. **LEARN** — query Qdrant RAG for exact SOC 2 control text
  3. **RECOMMEND** — Claude generates plain-English explanation + specific fix
  4. **MUTATE** — fetch file from GitHub, patch via LLM, open PR on branch `compliance-fix/<control_id>/<check_id>`
  5. **VALIDATE** — re-run scanner on patched file
- VALIDATE outcomes:
  - **PASS** → evidence store status updated to `remediated`
  - **FAIL** → Slack escalation, status updated to `escalated`, flagged for human review
- Evidence status transitions: `open → remediated | escalated | false_positive`
- Sequence diagram showing full flow from violation detection to PR merge

---

### `configuration.md`
**Audience:** Both

Full reference for all environment variables:

| Variable | Used by | Required | Default | Description |
|----------|---------|----------|---------|-------------|
| `DATABASE_URL` | store, api | Yes | `postgresql+asyncpg://...` | Postgres connection string |
| `REDIS_URL` | agents | Yes | `redis://localhost:6379` | Redis connection string |
| `ANTHROPIC_API_KEY` | brain/llm.py | Yes | — | Claude API key |
| `QDRANT_URL` | brain/rag.py | Yes | `http://localhost:6333` | Qdrant vector DB URL |
| `GITHUB_TOKEN` | mutate/ | Yes | — | GitHub PAT with `repo` scope |
| `GITHUB_WEBHOOK_SECRET` | api/webhooks.py | No | `""` | Webhook HMAC secret (skipped if unset) |
| `SLACK_WEBHOOK_URL` | notify/slack.py | No | — | Slack incoming webhook for escalations |

Additional sections:
- **GitHub webhook setup**: how to register `POST /webhook/github` with ngrok for local dev
- **Slack escalation setup**: how to create an incoming webhook in Slack and set `SLACK_WEBHOOK_URL`
- **Qdrant**: no config needed beyond `QDRANT_URL`; embeddings are loaded at startup automatically

---

### `troubleshooting.md`
**Audience:** Both

Common errors and fixes:

| Symptom | Cause | Fix |
|---------|-------|-----|
| `RuntimeError: checkov binary not found` | Checkov not installed | `pip install checkov` |
| `asyncpg.exceptions.ConnectionDoesNotExistError` | Postgres not running | `docker compose up postgres` |
| `redis.exceptions.ConnectionError` | Redis not running | `docker compose up redis` |
| Agent starts but no findings logged | `GITHUB_TOKEN` missing or wrong scope | Token needs `repo` scope |
| Remediation PR not opened | `GITHUB_TOKEN` insufficient permissions | Ensure token has write access to target repo |
| Slack alerts not firing | `SLACK_WEBHOOK_URL` not set | Add to `.env` and restart |
| `asyncio.TimeoutError` on Checkov scan | Large file or slow system | Increase `timeout` param in `CheckovRunner.scan()` |

- How to inspect evidence: `curl http://localhost:8000/evidence` or query Postgres directly
- How to read agent logs: `docker compose logs -f` or per-service `docker compose logs dev-team-agent`
- How to reset the evidence store: truncate `evidence_events` table in Postgres

---

## GitHub Sync Setup (one-time)

1. In GitBook: create a new Space → Integrations → GitHub → select this repo
2. Set sync directory to `docs/gitbook`
3. GitBook will read `SUMMARY.md` for navigation
4. Enable "Sync to GitHub" to allow GitBook edits to commit back to repo

---

## Out of Scope

- GitBook theme/branding customisation
- `brain/` and `dashboard/` internals
- Any code changes — documentation only
