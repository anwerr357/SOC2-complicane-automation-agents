# ComplyAgent — Continuous SOC 2 Compliance

📖 **Documentation:** [complyagents.gitbook.io/complyagentdoc](https://complyagents.gitbook.io/complyagentdoc/)

[![CI](https://github.com/your-org/complianceAgents/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/complianceAgents/actions/workflows/ci.yml)
[![GitBook](https://img.shields.io/badge/GitBook-Docs-blue)](https://complyagents.gitbook.io/complyagentdoc/)

An event-driven system of three autonomous AI agents that watch Kubernetes, Terraform, and GitHub 24/7 — detecting SOC 2 control violations in real time, explaining them in plain English, and automatically opening remediation pull requests.

---

## Why this exists

- **Compliance is continuous, not quarterly** — violations are detected the moment they occur, not weeks later during an audit
- **Manual evidence collection is eliminated** — every finding is automatically logged to an immutable Postgres audit trail
- **Engineers get fixes, not raw scanner output** — Claude translates violations into plain-English explanations and specific remediation PRs

---

## Architecture overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Event Sources                            │
│   GitHub webhooks   ·   Terraform plans   ·   Kubernetes watch   │
└───────────────┬──────────────────┬────────────────┬─────────────┘
                │                  │                │
                ▼                  ▼                ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Redis Streams (event bus)                   │
│      github.prs     ·     tf.plans     ·     k8s.events          │
└──────┬──────────────────────┬──────────────────┬────────────────┘
       │                      │                  │
       ▼                      ▼                  ▼
  Dev Team Agent        Policy Agent      Cluster Operator
  (Trufflehog +         (Checkov)         (k8s watch API)
   Semgrep)
       │                      │                  │
       └──────────────┬───────┘──────────────────┘
                      ▼
         ┌────────────────────────┐
         │   Compliance Brain     │
         │  Claude API + Qdrant   │
         │  (RAG on SOC 2 TSC)    │
         └────────────┬───────────┘
                      │
            ┌─────────▼──────────┐
            │  Remediation Loop  │
            │  Notify → Learn →  │
            │  Recommend →       │
            │  Mutate → Validate │
            └─────────┬──────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
   GitHub Pull Request      Postgres evidence
   (compliance-fix/*)        store (audit trail)
```

---

## What's implemented

| Capability | Module | Status | Doc |
|-----------|--------|--------|-----|
| Webhook server | `api/webhooks.py` | ✅ | [docs/webhooks.md](docs/webhooks.md) |
| Checkov runner | `scanners/checkov_runner.py` | ✅ | [docs/checkov_runner.md](docs/checkov_runner.md) |
| Evidence store | `store/` | ✅ | [docs/evidence_store.md](docs/evidence_store.md) |
| Redis event bus | `agents/base_agent.py` | ✅ | [AGENTS.md](AGENTS.md) |
| Compliance brain (RAG) | `brain/` | ✅ | [AGENTS.md](AGENTS.md) |
| Policy Agent | `agents/policy_agent.py` | ✅ | [docs/agents/policy_agent.md](docs/agents/policy_agent.md) |
| Cluster Operator Agent | `agents/cluster_operator.py` | ✅ | [docs/agents/cluster_operator.md](docs/agents/cluster_operator.md) |
| Dev Team Agent | `agents/dev_team_agent.py` | ✅ | [docs/agents/dev_team_agent.md](docs/agents/dev_team_agent.md) |
| Remediation loop | `agents/remediation.py`, `mutate/`, `notify/` | ✅ | [docs/remediation_loop.md](docs/remediation_loop.md) |
| Dashboard | `dashboard/` | ✅ | — |

---

## SOC 2 control coverage

| Control | Description | Agent | Scanner |
|---------|-------------|-------|---------|
| CC6.1 | Logical and physical access controls | Policy, Dev Team | Checkov, Trufflehog |
| CC6.2 | Authentication and MFA | Policy | Checkov |
| CC6.3 | Access removal | Dev Team | Semgrep |
| CC6.6 | Least privilege | Policy | Checkov |
| CC6.7 | Encryption at rest | Policy | Checkov |
| CC6.8 | Unauthorized software | Cluster Operator | k8s watch |
| CC7.1 | System monitoring | Cluster Operator | Checkov, k8s watch |
| CC7.2 | Audit logging | Cluster Operator, Dev Team | Semgrep, k8s watch |
| CC8.1 | Change management | Dev Team | Checkov, Semgrep |
| CC9.1 | Risk assessment | Policy | Checkov |
| A1.1 | Availability | Cluster Operator | k8s watch, Checkov |

---

## How to use

### Start the stack

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, GITHUB_TOKEN, SLACK_BOT_TOKEN (optional)

docker compose up --build
```

Services started:

| Service | URL |
|---------|-----|
| FastAPI + API docs | http://localhost:8000 / http://localhost:8000/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |
| Redis | localhost:6379 |
| Postgres | localhost:5432 |
| Dashboard | http://localhost:5173 |

### Trigger a scan manually

```bash
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "tests/fixtures/demo.tf", "git_sha": "abc123"}'
```

Returns a list of `CheckovFinding` objects — each carries `check_id`, `control_id`, and `severity`.

### Simulate a GitHub PR webhook (end-to-end agent flow)

```bash
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{"action": "opened", "pull_request": {"number": 42, "head": {"sha": "abc123", "repo": {"full_name": "org/repo"}}}}'
```

This triggers the Dev Team Agent: shallow-clone the PR branch → Trufflehog + Semgrep → brain RAG lookup → Claude explanation → remediation PR if violations found.

### Query evidence

```bash
curl http://localhost:8000/evidence           # all recent findings
curl http://localhost:8000/evidence/CC6.7     # filter by SOC 2 control
```

---

## Local development

### Prerequisites

- Docker + Docker Compose v2
- Python 3.12
- `pip install checkov`

### Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://complyagent:complyagentsecret@localhost:5432/compliance` | Postgres connection |
| `REDIS_URL` | Yes | `redis://localhost:6379` | Redis connection |
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `QDRANT_URL` | Yes | `http://localhost:6333` | Qdrant vector DB |
| `GITHUB_TOKEN` | Yes | — | PAT with `repo` scope |
| `GITHUB_REPO_OWNER` | Yes | — | GitHub org/user owning the target repo |
| `GITHUB_REPO_NAME` | Yes | — | Target repo name |
| `GITHUB_WEBHOOK_SECRET` | No | `""` | Webhook HMAC secret (skipped if unset) |
| `SLACK_BOT_TOKEN` | No | — | Slack bot token for escalation alerts |
| `SLACK_ALERT_CHANNEL` | No | `#compliance-alerts` | Slack channel for alerts |

---

## Project structure

```
complianceAgents/
├── agents/
│   ├── base_agent.py          — Redis Streams consumer base class
│   ├── policy_agent.py        — Terraform + K8s governance (Checkov)
│   ├── cluster_operator.py    — Live K8s + Prometheus drift detection
│   ├── dev_team_agent.py      — PR scanning (Trufflehog + Semgrep)
│   └── remediation.py         — Shared 5-step remediation loop
├── brain/
│   ├── embeddings.py          — SOC 2 control text → Qdrant vectors
│   ├── rag.py                 — Retrieval pipeline
│   └── llm.py                 — Claude API client (structured output)
├── scanners/
│   ├── checkov_runner.py      — IaC scanner wrapper
│   ├── trufflehog_runner.py   — Secret detection wrapper
│   ├── semgrep_runner.py      — SAST wrapper
│   └── k8s_watcher.py         — Kubernetes watch API client
├── mutate/
│   ├── mutate.py              — GitHub PR creation
│   └── validate.py            — Post-remediation re-scan
├── notify/
│   └── slack.py               — Slack escalation notifications
├── store/
│   ├── models.py              — SQLAlchemy ORM (evidence_events)
│   └── evidence.py            — Async DB helpers
├── api/
│   └── webhooks.py            — FastAPI app
├── dashboard/                 — React + Tailwind dashboard
├── semgrep_rules/             — Custom Semgrep YAML rules
├── tests/                     — pytest suite
├── docs/                      — Developer documentation
├── .github/workflows/ci.yml   — GitHub Actions CI
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── AGENTS.md                  — Agent roster and communication contract
└── README.md
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 (async throughout) |
| Agent orchestration | LangGraph |
| LLM | Claude API (`claude-sonnet-4-6`) |
| Vector DB | Qdrant |
| Event bus | Redis Streams |
| IaC scanner | Checkov |
| Secret scanner | Trufflehog |
| SAST | Semgrep |
| K8s client | kubernetes-asyncio |
| GitHub API | PyGithub |
| Web framework | FastAPI |
| ORM | SQLAlchemy 2.0 async |
| Database | Postgres 16 |
| Dashboard | React + Tailwind + Recharts |
| CI | GitHub Actions |
| Local dev | Docker Compose |
