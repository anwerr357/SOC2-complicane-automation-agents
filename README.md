# ComplyAgent — Continuous SOC 2 Compliance

An event-driven system of three autonomous AI agents that watch Kubernetes,
Terraform, and GitHub 24/7 — detecting SOC 2 control violations in real time,
explaining them in plain English, and automatically opening remediation pull
requests.

---

## Why this exists

Most teams treat compliance as a quarterly audit event.  Violations sit
undetected for weeks.  Manual evidence collection is slow.  Engineers spend
hours translating raw scanner output into fixes.  This system makes compliance
**continuous and automated**.

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

## Components

### 1. FastAPI webhook server (`api/webhooks.py`)

The single entry point for all inbound events.  Receives GitHub webhooks
(push and pull_request events) and Prometheus Alertmanager payloads.
Exposes a `/scan/checkov` endpoint for manual and CI-triggered scans.

**Week 1 scope:** skeleton + `/scan/checkov` endpoint fully wired to Checkov
runner + Postgres evidence store.

```bash
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "tests/fixtures/demo.tf", "git_sha": "abc123"}'
```

### 2. Checkov scanner runner (`scanners/checkov_runner.py`)

Async subprocess wrapper around the [Checkov](https://www.checkov.io/) IaC
scanner.  Accepts a Terraform `.tf` or Kubernetes YAML file, runs
`checkov --output json`, parses the result, and maps every failed check to a
SOC 2 Trust Service Criterion using a curated lookup table.

**Example mapping:**

| Checkov check  | Resource            | SOC 2 control |
|----------------|---------------------|---------------|
| `CKV_AWS_19`   | `aws_s3_bucket`     | CC6.7 — Encryption at rest |
| `CKV_AWS_40`   | `aws_iam_role_policy` | CC6.1 — Logical access |
| `CKV_AWS_36`   | `aws_cloudtrail`    | CC7.2 — Audit logging |
| `CKV_K8S_8`    | `Deployment`        | A1.1 — Availability |

Returns a list of `CheckovFinding` dataclasses ready for `log_event()`.

### 3. Postgres evidence store (`store/`)

**`store/models.py`** — SQLAlchemy ORM model for the `evidence_events` table.
Every violation ever detected gets a permanent row here.  Nothing is deleted;
status columns are updated in-place as findings move through the remediation
loop.

Key columns:
- `control_id` — SOC 2 criterion (CC6.7, A1.1, …)
- `check_id` — scanner-native ID (CKV_AWS_19, semgrep-rule-id, …)
- `status` — `open | remediated | escalated | false_positive`
- `raw_finding` — JSONB — full scanner payload, never discarded
- `pr_url` — GitHub PR URL once remediation is opened

**`store/evidence.py`** — async helper functions: `init_db()`, `log_event()`,
`update_remediation()`, `get_recent_events()`.

### 4. Redis Streams event bus

Sources publish to named streams.  Agents subscribe only to relevant streams.
Sources don't know who's listening.  Agents don't know who sent the event.

| Stream               | Published by                  | Consumed by                        |
|----------------------|-------------------------------|------------------------------------|
| `github.prs`         | FastAPI GitHub webhook        | Dev Team Agent                     |
| `tf.plans`           | FastAPI / CI trigger          | Policy Agent                       |
| `k8s.events`         | Kubernetes watcher            | Policy Agent, Cluster Operator     |
| `prometheus.alerts`  | FastAPI Prometheus webhook    | (future: Availability Agent)       |

**Why Redis Streams over Kafka/RabbitMQ:**  Compliance events are low volume
(~20/day).  Kafka is overkill for this throughput.  RabbitMQ uses a queue
model — messages disappear after consumption.  Redis Streams give us a
persistent log with consumer group replay when an agent restarts after a crash.

### 5. Compliance brain (`brain/`)

Shared by all three agents.  SOC 2 Trust Service Criteria text embedded into
Qdrant at startup.  When a scanner finds a violation, the agent queries Qdrant
with the violation description to retrieve the matching control text.  That
text + the raw finding are sent to Claude to generate a plain-English
explanation and specific remediation step.

**Implemented in Week 3.**

### 6. Remediation mutator (`mutate/`)

GitOps-first: fixes never apply directly to the cluster.

1. Fetch the violating file from GitHub via PyGithub
2. LLM patches the file content
3. Create branch `compliance-fix/<control_id>/<check_id>`
4. Push commit, open PR with SOC 2 control ID in title
5. Re-run scanner on patched content to validate

**Implemented in Weeks 2 and 5.**

---

## Getting started

### Prerequisites

- Docker + Docker Compose v2
- Python 3.12 (for local development without Docker)
- `checkov` (`pip install checkov`)

### Start the full stack

```bash
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY and GITHUB_TOKEN

docker compose up --build
```

Services:
- FastAPI:  http://localhost:8000
- API docs: http://localhost:8000/docs
- Qdrant:   http://localhost:6333/dashboard

### Run your first scan (no GitHub token needed)

```bash
# The demo fixture has intentional violations seeded in
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "tests/fixtures/demo.tf"}'
```

### View evidence

```bash
curl http://localhost:8000/evidence
curl http://localhost:8000/evidence/CC6.7
```

### Run tests locally

```bash
pip install checkov -r requirements.txt
pytest tests/ -v
```

---

## 6-week build plan

| Week | Scope | Status |
|------|-------|--------|
| **1** | Foundations — Docker Compose, Checkov runner, Postgres schema, FastAPI skeleton | ✅ Done |
| **2** | GitHub integration — PyGithub PR mutation flow, branch + commit + PR creation | 🔜 Next |
| **3** | Compliance brain — Qdrant embeddings, RAG pipeline, Trufflehog + Semgrep | ⏳ |
| **4** | Live K8s watcher — kubernetes-asyncio, Redis Streams event bus | ⏳ |
| **5** | Multi-agent orchestration — LangGraph state machines, full 5-step loop | ⏳ |
| **6** | Dashboard + polish — React + Recharts, AGENTS.md, end-to-end demo | ⏳ |

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
| A1.1  | Availability | Cluster Operator | k8s watch, Checkov |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 (async throughout) |
| Agent orchestration | LangGraph |
| LLM | Claude API (`claude-sonnet-4-20250514`) |
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
| Dashboard | React + Recharts (Week 6) |
| CI | GitHub Actions |
| Local dev | Docker Compose |

---

## Project structure

```
complyagent/
├── agents/
│   ├── policy_agent.py        — Terraform + K8s governance (Checkov)
│   ├── cluster_operator.py    — Live K8s drift detection
│   └── dev_team_agent.py      — PR scanning (Trufflehog + Semgrep)
├── brain/
│   ├── embeddings.py          — SOC 2 control text → Qdrant vectors
│   ├── rag.py                 — Retrieval pipeline
│   └── llm.py                 — Claude API client (structured output)
├── scanners/
│   ├── checkov_runner.py      — IaC scanner wrapper ✅
│   ├── trufflehog_runner.py   — Secret detection wrapper
│   ├── semgrep_runner.py      — SAST wrapper with custom rules
│   └── k8s_watcher.py         — Kubernetes watch API client
├── mutate/
│   ├── mutate.py              — GitHub PR creation
│   └── validate.py            — Post-remediation re-scan
├── store/
│   ├── models.py              — SQLAlchemy ORM (evidence_events) ✅
│   └── evidence.py            — Async DB helpers ✅
├── api/
│   └── webhooks.py            — FastAPI app ✅
├── tests/
│   ├── test_checkov_runner.py — Checkov integration tests ✅
│   └── fixtures/demo.tf       — Seeded-violation Terraform file ✅
├── dashboard/                 — React app (Week 6)
├── .github/workflows/ci.yml   — GitHub Actions CI ✅
├── docker-compose.yml         — Full local stack ✅
├── Dockerfile
├── requirements.txt
├── AGENTS.md                  — Agent roster and communication contract
└── README.md
```
