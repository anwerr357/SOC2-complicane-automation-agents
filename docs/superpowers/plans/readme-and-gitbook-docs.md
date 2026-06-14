# README & GitBook Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the README, update in-repo developer docs, and create a full GitBook documentation site (10 pages) synced from `docs/gitbook/` — all targeting developer onboarding and operator usage.

**Architecture:** Two phases. Phase 1 updates in-repo markdown (README + satellite docs). Phase 2 creates the `docs/gitbook/` tree for GitBook GitHub sync. Both are documentation-only — no code changes.

**Tech Stack:** Markdown, GitBook GitHub sync (`SUMMARY.md` as nav), existing project stack for accurate examples.

---

## File Map

**Phase 1 — In-repo docs**

| Action | File |
|--------|------|
| Modify | `README.md` |
| Modify | `docs/index.md` |
| Create | `docs/agents/policy_agent.md` |
| Create | `docs/agents/cluster_operator.md` |
| Create | `docs/agents/dev_team_agent.md` |
| Create | `docs/remediation_loop.md` |

**Phase 2 — GitBook docs**

| Action | File |
|--------|------|
| Create | `docs/gitbook/SUMMARY.md` |
| Create | `docs/gitbook/introduction.md` |
| Create | `docs/gitbook/installation.md` |
| Create | `docs/gitbook/quick-start.md` |
| Create | `docs/gitbook/how-to-use/README.md` |
| Create | `docs/gitbook/how-to-use/policy-agent.md` |
| Create | `docs/gitbook/how-to-use/cluster-operator-agent.md` |
| Create | `docs/gitbook/how-to-use/dev-team-agent.md` |
| Create | `docs/gitbook/how-to-use/remediation-loop.md` |
| Create | `docs/gitbook/configuration.md` |
| Create | `docs/gitbook/troubleshooting.md` |

---

## Phase 1 — In-Repo Docs

---

### Task 1: Rewrite README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace README.md with the updated content**

Write the following content to `README.md`:

```markdown
# ComplyAgent — Continuous SOC 2 Compliance

[![CI](https://github.com/your-org/complianceAgents/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/complianceAgents/actions/workflows/ci.yml)

An event-driven system of three autonomous AI agents that watch Kubernetes, Terraform, and GitHub 24/7 — detecting SOC 2 control violations in real time, explaining them in plain English, and automatically opening remediation pull requests.

---

## Why this exists

- **Compliance is continuous, not quarterly** — violations are detected the moment they occur, not weeks later during an audit
- **Manual evidence collection is eliminated** — every finding is automatically logged to an immutable Postgres audit trail
- **Engineers get fixes, not raw scanner output** — Claude translates violations into plain-English explanations and specific remediation PRs

---

## Architecture overview

\```
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
\```

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

\```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, GITHUB_TOKEN, SLACK_BOT_TOKEN (optional)

docker compose up --build
\```

Services started:

| Service | URL |
|---------|-----|
| FastAPI + API docs | http://localhost:8000 / http://localhost:8000/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |
| Redis | localhost:6379 |
| Postgres | localhost:5432 |
| Dashboard | http://localhost:5173 |

### Trigger a scan manually

\```bash
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "tests/fixtures/demo.tf", "git_sha": "abc123"}'
\```

Returns a list of `CheckovFinding` objects — each carries `check_id`, `control_id`, and `severity`.

### Simulate a GitHub PR webhook (end-to-end agent flow)

\```bash
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{"action": "opened", "pull_request": {"number": 42, "head": {"sha": "abc123", "repo": {"full_name": "org/repo"}}}}'
\```

This triggers the Dev Team Agent: shallow-clone the PR branch → Trufflehog + Semgrep → brain RAG lookup → Claude explanation → remediation PR if violations found.

### Query evidence

\```bash
curl http://localhost:8000/evidence           # all recent findings
curl http://localhost:8000/evidence/CC6.7     # filter by SOC 2 control
\```

---

## Local development

### Prerequisites

- Docker + Docker Compose v2
- Python 3.12
- `pip install checkov`

### Run tests

\```bash
pip install -r requirements.txt
pytest tests/ -v
\```

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

\```
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
\```

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
```

- [ ] **Step 2: Verify the file renders correctly**

Open `README.md` and confirm:
- Feature matrix table has 10 rows, all ✅
- "How to use" section has 4 sub-sections with curl examples
- Project structure tree includes `notify/`, `agents/remediation.py`, `semgrep_rules/`
- No stray `\` escapes left in code blocks (they were used for escaping in this plan only)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README with feature matrix and how-to-use section"
```

---

### Task 2: Update docs/index.md

**Files:**
- Modify: `docs/index.md`

- [ ] **Step 1: Replace docs/index.md with the updated content**

Write the following to `docs/index.md`:

```markdown
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
```

- [ ] **Step 2: Verify the file**

Confirm the module map table has 13 rows covering all modules, and the data flow diagram shows all 3 agents feeding `run_remediation_loop()`.

- [ ] **Step 3: Commit**

```bash
git add docs/index.md
git commit -m "docs: update index to reflect full system data flow and module map"
```

---

### Task 3: Create docs/agents/policy_agent.md

**Files:**
- Create: `docs/agents/policy_agent.md`

- [ ] **Step 1: Create the agents directory and write policy_agent.md**

```bash
mkdir -p docs/agents
```

Write the following to `docs/agents/policy_agent.md`:

```markdown
# Policy Agent

**Module:** `agents/policy_agent.py`
**Class:** `PolicyAgent(BaseAgent)`

---

## Purpose

Governance watcher for Terraform infrastructure and Kubernetes manifests. Runs Checkov against every plan before it reaches the cluster, enforcing SOC 2 controls at the IaC layer.

---

## Redis streams consumed

| Stream | Trigger |
|--------|---------|
| `tf.plans` | A Terraform plan file is ready for scanning (published by CI or the webhook server) |
| `k8s.events` | A Kubernetes manifest event carrying a `control_id` owned by this agent |

**Controls owned:** `CC6.1`, `CC6.6`, `CC6.7`, `CC9.1`

The agent silently drops events whose `control_id` it does not own — no cross-agent coupling required.

---

## How it works

### Terraform plan flow (`tf.plans`)

1. Receives event: `{"file_path": "infra/main.tf", "git_sha": "abc123", "repo_file_path": "infra/main.tf"}`
2. Calls `run_checkov(file_path, git_sha=git_sha)` — returns `list[CheckovFinding]`
3. Filters findings to only those whose `control_id` is in `CONTROLS`
4. For each owned finding, calls `run_remediation_loop(finding, repo_full_name=..., github_token=...)`

### Kubernetes event flow (`k8s.events`)

1. Receives event from the Kubernetes watcher with `control_id`, `check_id`, `resource_kind`, `resource_name`, `namespace`, `violation`
2. Drops events with `control_id` not in `CONTROLS`
3. Builds a finding dict and calls `run_remediation_loop()`

---

## Example end-to-end

**Violation:** `infra/main.tf` defines an S3 bucket without `server_side_encryption_configuration`.

```
Checkov → CKV2_AWS_61 → CC6.7 (Encryption at rest)
  └── run_remediation_loop()
        ├── NOTIFY   → evidence_events row inserted, status=open
        ├── LEARN    → Qdrant returns CC6.7 control text
        ├── RECOMMEND → Claude: "This S3 bucket stores sensitive data without encryption..."
        ├── MUTATE   → PR opened: compliance-fix/CC6.7/CKV2_AWS_61
        └── VALIDATE → Checkov re-runs on patched file → PASS → status=remediated
```

---

## How to extend

**Add a new Checkov rule mapping:**

Open `scanners/checkov_runner.py` and add one line to `SOC2_CONTROL_MAP`:

```python
"CKV_AWS_XYZ": ("CC6.7", "Encryption at rest"),
```

No other files need to change. The new mapping is active on the next scan.

**Add a new control to this agent:**

Add the control ID string to `PolicyAgent.CONTROLS` in `agents/policy_agent.py`:

```python
CONTROLS = ["CC6.1", "CC6.6", "CC6.7", "CC9.1", "CC6.2"]
```
```

- [ ] **Step 2: Verify the file**

Confirm the example flow shows all 5 remediation steps and the branch name matches `compliance-fix/<control_id>/<check_id>`.

- [ ] **Step 3: Commit**

```bash
git add docs/agents/policy_agent.md
git commit -m "docs: add Policy Agent developer reference"
```

---

### Task 4: Create docs/agents/cluster_operator.md

**Files:**
- Create: `docs/agents/cluster_operator.md`

- [ ] **Step 1: Write docs/agents/cluster_operator.md**

```markdown
# Cluster Operator Agent

**Module:** `agents/cluster_operator.py`
**Class:** `ClusterOperatorAgent(BaseAgent)`

---

## Purpose

Watches live Kubernetes cluster state and Prometheus alerts for runtime violations — things that happen *after* manifests are deployed and that static Checkov scans cannot see.

---

## Redis streams consumed

| Stream | Trigger |
|--------|---------|
| `k8s.events` | A Kubernetes resource change event from the live watcher |
| `prometheus.alerts` | A Prometheus Alertmanager alert payload |

**Controls owned:** `CC7.1`, `CC7.2`, `A1.1`, `CC6.8`

---

## What it catches that Checkov misses

Checkov scans static IaC files — it checks what *should* be deployed. This agent watches what *is actually running*. The key signal: a `kubectl edit` on a production resource that bypasses the GitOps pipeline entirely never touches a `.tf` or `.yaml` file in Git, so Checkov never sees it.

---

## How it works

### Kubernetes event flow (`k8s.events`)

1. Receives event from the Kubernetes watcher (published by `scanners/k8s_watcher.py`)
2. Calls `run_remediation_loop()` with the drift finding

### Prometheus alert flow (`prometheus.alerts`)

1. Receives Alertmanager payload: `{"alerts": [{"labels": {"alertname": "CrashLoopBackOff", "severity": "critical"}, ...}]}`
2. Maps `alertname` substrings to SOC 2 controls via `_ALERT_CONTROL_MAP`:
   - `crashloop`, `nodenotready`, `oomkill` → `A1.1` (Availability)
   - `unauthorized`, `suspicious`, `intrusion` → `CC6.8` (Unauthorized software)
   - `auditlog`, `logging` → `CC7.2` (Audit logging)
   - Anything else → `CC7.1` (System monitoring) as default
3. Calls `run_remediation_loop()`

---

## Example end-to-end

**Violation:** An engineer runs `kubectl edit deployment/api` directly on production, adding a `hostPath` volume mount that bypasses GitOps.

```
k8s watcher detects drift → k8s.events stream
  └── ClusterOperatorAgent.handle_event()
        └── run_remediation_loop()
              ├── NOTIFY   → evidence_events row inserted, status=open
              ├── LEARN    → Qdrant returns CC6.6 control text
              ├── RECOMMEND → Claude: "A hostPath mount on the api deployment..."
              ├── MUTATE   → k8s_watch findings are NOT auto-patched via PR
              │              (scanner_used="k8s_watch" is outside _VALIDATE_SUPPORTED)
              └── VALIDATE → skipped → ESCALATE → Slack alert + status=escalated
```

> **Note:** K8s drift findings always escalate to Slack rather than opening a PR. This is by design — live cluster state requires human review before remediation. Only `checkov`, `semgrep`, and `trufflehog` findings go through the full MUTATE → VALIDATE path.

---

## How to extend

**Add a new Prometheus alert → control mapping:**

Open `agents/cluster_operator.py` and add a tuple to `_ALERT_CONTROL_MAP`:

```python
(
    ("diskencryption", "unencryptedvolume"),
    ("CC6.7", "Encryption at rest"),
),
```

Keywords are matched as substrings (case-insensitive) against `alertname`. First match wins.
```

- [ ] **Step 2: Verify the file**

Confirm the note about `k8s_watch` always escalating (not auto-remediating) is present — this is the key behaviour that distinguishes this agent.

- [ ] **Step 3: Commit**

```bash
git add docs/agents/cluster_operator.md
git commit -m "docs: add Cluster Operator Agent developer reference"
```

---

### Task 5: Create docs/agents/dev_team_agent.md

**Files:**
- Create: `docs/agents/dev_team_agent.md`

- [ ] **Step 1: Write docs/agents/dev_team_agent.md**

```markdown
# Dev Team Agent

**Module:** `agents/dev_team_agent.py`
**Class:** `DevTeamAgent(BaseAgent)`

---

## Purpose

PR-level compliance gatekeeper. Shallow-clones every pull request branch and runs two scanner chains: Trufflehog for secret detection across the full commit history, and Semgrep for code-level compliance patterns using custom rules.

---

## Redis streams consumed

| Stream | Trigger |
|--------|---------|
| `github.prs` | A pull request is opened or synchronised on GitHub |

**Controls owned:** `CC6.1`, `CC7.2`, `CC8.1`, `CC6.3`

---

## How it works

1. Receives event: `{"repo_full_name": "org/repo", "pr_number": 42, "head_sha": "abc123"}`
2. Shallow-clones the PR branch into a temp directory using a token-auth git askpass helper (token never written to disk)
3. **Trufflehog:** Scans full git history of the cloned branch for live secrets — API keys, tokens, certificates
4. **Semgrep:** Runs custom rules from `semgrep_rules/` against the working tree
5. For each finding from either scanner, calls `run_remediation_loop()`
6. Temp directory is always cleaned up, even on error

---

## Scanner chain

```
github.prs event
    │
    ▼
shallow_clone(repo, sha, token) → /tmp/clone-xxxx/
    │
    ├── TrufflehogRunner.scan(clone_dir)
    │       └── findings: list[TrufflehogFinding]
    │
    └── SemgrepRunner.scan(clone_dir)
            └── findings: list[SemgrepFinding]
    │
    ▼
for finding in all_findings:
    run_remediation_loop(finding, repo_full_name, github_token)
    │
    ├── PASS → PR opens: compliance-fix/<control_id>/<check_id>
    └── FAIL → Slack escalation
```

---

## Example end-to-end

**Violation:** A new `/api/users` POST endpoint writes to the database but never calls `audit_log()`.

```
PR opened → github.prs stream
  └── DevTeamAgent.handle_event()
        ├── Trufflehog → no secrets found
        └── Semgrep → custom rule fires: missing audit_log() call
              control_id: CC7.2 (Audit logging)
              └── run_remediation_loop()
                    ├── NOTIFY   → evidence row inserted
                    ├── LEARN    → Qdrant returns CC7.2 control text
                    ├── RECOMMEND → Claude: "This endpoint writes user data..."
                    ├── MUTATE   → PR opened: compliance-fix/CC7.2/semgrep-audit-log
                    └── VALIDATE → Semgrep re-runs → PASS → status=remediated
```

---

## Custom Semgrep rules

Rules live in `semgrep_rules/` as YAML files. Three rules ship out of the box:

| File | What it catches | Control |
|------|----------------|---------|
| `audit_log.yaml` | Functions that write to DB without calling `audit_log()` | CC7.2 |
| `hardcoded_secret.yaml` | String literals that look like API keys or passwords | CC6.1 |
| `dangerous_eval.yaml` | Use of `eval()` or `exec()` with dynamic input | CC8.1 |

**Add a new rule:**

Create a new `.yaml` file in `semgrep_rules/` following the Semgrep rule schema:

```yaml
rules:
  - id: require-rate-limit-on-auth-endpoints
    patterns:
      - pattern: |
          @app.route("/login", ...)
          def $FUNC(...):
              ...
    message: "Auth endpoint missing rate limiting — CC6.2 violation"
    languages: [python]
    severity: WARNING
    metadata:
      control_id: CC6.2
      control_name: "Authentication and MFA"
```

No other files need to change. `SemgrepRunner` discovers all `.yaml` files in the rules directory automatically.
```

- [ ] **Step 2: Verify the file**

Confirm the scanner chain diagram shows both Trufflehog and Semgrep feeding `run_remediation_loop()`, and the three existing rules are listed with their control IDs.

- [ ] **Step 3: Commit**

```bash
git add docs/agents/dev_team_agent.md
git commit -m "docs: add Dev Team Agent developer reference"
```

---

### Task 6: Create docs/remediation_loop.md

**Files:**
- Create: `docs/remediation_loop.md`

- [ ] **Step 1: Write docs/remediation_loop.md**

```markdown
# The Remediation Loop

**Module:** `agents/remediation.py`
**Entry point:** `run_remediation_loop(finding, *, repo_full_name, github_token) → LoopOutcome`

---

## Overview

Every agent feeds violations into the same 5-step loop. The loop is shared, so adding a new agent requires zero changes to remediation logic.

```
NOTIFY → LEARN → RECOMMEND → MUTATE → VALIDATE
```

---

## The 5 steps

### Step 1 — NOTIFY

Inserts a row into `evidence_events` in Postgres with `status=open`. This is the immutable audit record — it exists regardless of what happens in subsequent steps.

```python
async with get_session() as session:
    event = await log_event(session, finding)
    event_id = event.id
```

### Step 2 — LEARN

Queries Qdrant for the SOC 2 control text matching `control_id`. Returns the exact Trust Service Criterion wording used by auditors.

```python
control = await retrieve_by_control_id(control_id, QDRANT_URL)
# control.text → "The entity restricts logical access to information assets..."
```

### Step 3 — RECOMMEND

Sends the violation + control text to Claude. Returns a structured `ExplanationOutput` with:
- `violation_summary` — plain-English description of what's wrong
- `business_impact` — why this matters for SOC 2 compliance
- `remediation_steps` — specific, actionable fix instructions

```python
explanation = await generate_explanation(
    check_id=check_id,
    control_id=control_id,
    control_text=control.text,
    resource_name=finding["resource_name"],
    ...
)
```

### Step 4 — MUTATE

Opens a remediation PR on GitHub:

1. Fetches the violating file via PyGithub
2. Sends file content + violation description to Claude for patching
3. Creates branch: `compliance-fix/<control_id>/<check_id>`
4. Commits the patched file
5. Opens PR with title: `[<control_id>] Fix: <violation summary>`

```python
pr_url = await open_remediation_pr(
    finding=finding,
    explanation=enriched,
    repo_full_name=repo_full_name,
    github_token=github_token,
)
```

> **K8s drift findings skip MUTATE.** `scanner_used="k8s_watch"` is not in `_VALIDATE_SUPPORTED`. These findings jump straight to escalation — live cluster state requires human review.

### Step 5 — VALIDATE

Re-runs the original scanner on the patched file content.

**PASS:** Scanner finds no violations → `update_remediation(event_id, pr_url)` → `status=remediated`

**FAIL:** Scanner still finds violations → `escalate_event(event_id, detail)` → `status=escalated` → Slack alert sent via `post_escalation()`

---

## Evidence status transitions

```
open
 ├── → remediated      (VALIDATE PASS)
 ├── → escalated       (VALIDATE FAIL, or k8s_watch finding)
 └── → false_positive  (manual update via evidence store)
```

Status only ever moves forward. Rows are never deleted.

---

## Outcome object

```python
@dataclass
class LoopOutcome:
    status: str            # "REMEDIATED" | "ESCALATED" | "ERROR"
    pr_url: str | None     # GitHub PR URL if MUTATE succeeded
    detail: str            # Human-readable explanation of the outcome
```

---

## Sequence diagram

```
Agent          remediation.py       Postgres      Qdrant        Claude        GitHub        Slack
─────          ──────────────       ────────      ──────        ──────        ──────        ─────

finding ──►  run_remediation_loop()
                │
                │  log_event()
                ├──────────────►  INSERT
                │◄──────────────  event_id
                │
                │  retrieve_by_control_id()
                ├─────────────────────────►  search
                │◄─────────────────────────  control text
                │
                │  generate_explanation()
                ├──────────────────────────────────►  prompt
                │◄──────────────────────────────────  ExplanationOutput
                │
                │  open_remediation_pr()
                ├───────────────────────────────────────────►  branch+commit+PR
                │◄───────────────────────────────────────────  pr_url
                │
                │  validate_remediation()  [re-scan]
                │
                ├── PASS ──►  update_remediation()  ──►  status=remediated
                │
                └── FAIL ──►  escalate_event()  ──►  status=escalated
                              post_escalation()  ─────────────────────────►  Slack alert
```
```

- [ ] **Step 2: Verify the file**

Confirm the sequence diagram shows all 5 steps and both PASS/FAIL branches. Confirm the note about `k8s_watch` findings skipping MUTATE is present.

- [ ] **Step 3: Commit**

```bash
git add docs/remediation_loop.md
git commit -m "docs: add remediation loop developer reference"
```

---

## Phase 2 — GitBook Docs

---

### Task 7: Create GitBook scaffold (SUMMARY.md + directory structure)

**Files:**
- Create: `docs/gitbook/SUMMARY.md`
- Create: `docs/gitbook/how-to-use/` (directory)

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p docs/gitbook/how-to-use
```

- [ ] **Step 2: Write docs/gitbook/SUMMARY.md**

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

- [ ] **Step 3: Commit**

```bash
git add docs/gitbook/SUMMARY.md
git commit -m "docs: add GitBook scaffold and SUMMARY.md navigation"
```

---

### Task 8: Write docs/gitbook/introduction.md

**Files:**
- Create: `docs/gitbook/introduction.md`

- [ ] **Step 1: Write the file**

```markdown
# Introduction

ComplyAgent is an event-driven system of three autonomous AI agents that watch your Kubernetes cluster, Terraform infrastructure, and GitHub pull requests 24/7. When a SOC 2 control violation is detected, the system explains it in plain English and automatically opens a remediation pull request — without any human intervention.

---

## The problem it solves

Most engineering teams treat SOC 2 compliance as a quarterly event. An auditor arrives, requests evidence, and violations that have been sitting undetected for weeks are discovered under pressure. Manual evidence collection is slow. Engineers spend hours translating raw scanner output (`CKV_AWS_19 FAILED`) into something actionable.

ComplyAgent makes compliance **continuous and automated**:

- Violations are detected the moment they occur — not weeks later
- Every finding is logged automatically to an immutable audit trail
- Engineers receive specific, LLM-generated remediation PRs instead of raw scanner JSON

---

## Architecture

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
                      ▼
            ┌─────────────────────┐
            │  Remediation Loop   │
            │  5 automated steps  │
            └─────────┬───────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
   GitHub Pull Request      Postgres evidence
   (compliance-fix/*)        store (audit trail)
```

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
| CC7.1 | System monitoring | Cluster Operator | k8s watch |
| CC7.2 | Audit logging | Cluster Operator, Dev Team | Semgrep, k8s watch |
| CC8.1 | Change management | Dev Team | Semgrep |
| CC9.1 | Risk assessment | Policy | Checkov |
| A1.1 | Availability | Cluster Operator | k8s watch, Checkov |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 (async throughout) |
| Agent orchestration | LangGraph |
| LLM | Claude (`claude-sonnet-4-6`) |
| Vector DB | Qdrant |
| Event bus | Redis Streams |
| IaC scanner | Checkov |
| Secret scanner | Trufflehog |
| SAST | Semgrep |
| K8s client | kubernetes-asyncio |
| GitHub API | PyGithub |
| Web framework | FastAPI |
| Database | Postgres 16 |
| Dashboard | React + Tailwind |

---

Next: [Installation →](installation.md)
```

- [ ] **Step 2: Commit**

```bash
git add docs/gitbook/introduction.md
git commit -m "docs: add GitBook introduction page"
```

---

### Task 9: Write docs/gitbook/installation.md

**Files:**
- Create: `docs/gitbook/installation.md`

- [ ] **Step 1: Write the file**

```markdown
# Installation

---

## Prerequisites

- **Docker** + **Docker Compose v2** — all services run in containers
- **Python 3.12** — only needed for running tests locally without Docker
- **Checkov** — only needed for local test runs: `pip install checkov`

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/your-org/complianceAgents.git
cd complianceAgents
```

---

## Step 2 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
GITHUB_REPO_OWNER=your-org
GITHUB_REPO_NAME=your-repo

# Optional — needed for Slack escalation alerts
SLACK_BOT_TOKEN=xoxb-...
SLACK_ALERT_CHANNEL=#compliance-alerts
```

See [Configuration](configuration.md) for the full variable reference.

---

## Step 3 — Start the stack

```bash
docker compose up --build
```

First run takes ~3 minutes to pull images and build the Python container.

---

## Services

| Service | URL | Description |
|---------|-----|-------------|
| FastAPI | http://localhost:8000 | Main API — webhooks, scan triggers, evidence read |
| API docs | http://localhost:8000/docs | Swagger UI |
| Qdrant | http://localhost:6333/dashboard | Vector DB dashboard |
| Redis | localhost:6379 | Event bus (no UI) |
| Postgres | localhost:5432 | Evidence store (no UI) |
| Dashboard | http://localhost:5173 | React compliance dashboard |

---

## Verify the installation

```bash
curl http://localhost:8000/healthz
# → {"status": "ok"}
```

---

Next: [Quick Start →](quick-start.md)
```

- [ ] **Step 2: Commit**

```bash
git add docs/gitbook/installation.md
git commit -m "docs: add GitBook installation page"
```

---

### Task 10: Write docs/gitbook/quick-start.md

**Files:**
- Create: `docs/gitbook/quick-start.md`

- [ ] **Step 1: Write the file**

```markdown
# Quick Start

Run your first compliance scan and see results in under 5 minutes.

---

## 1. Start the stack

```bash
docker compose up --build
```

Wait until you see `Application startup complete` in the FastAPI logs.

---

## 2. Trigger a Checkov scan on the demo fixture

The repo ships with `tests/fixtures/demo.tf` — a Terraform file with intentional violations seeded in.

```bash
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "tests/fixtures/demo.tf", "git_sha": "abc123"}'
```

You'll receive a JSON array of findings:

```json
[
  {
    "check_id": "CKV2_AWS_61",
    "control_id": "CC6.7",
    "control_name": "Encryption at rest",
    "resource_name": "aws_s3_bucket.app_data",
    "severity": "MEDIUM",
    "file_path": "tests/fixtures/demo.tf"
  },
  {
    "check_id": "CKV_AWS_289",
    "control_id": "CC6.6",
    "control_name": "Least privilege and logical access restriction",
    "resource_name": "aws_iam_role_policy.app_policy",
    "severity": "HIGH",
    "file_path": "tests/fixtures/demo.tf"
  }
]
```

---

## 3. View evidence

Findings are automatically logged to the Postgres evidence store.

```bash
# All recent findings
curl http://localhost:8000/evidence

# Filter by SOC 2 control
curl http://localhost:8000/evidence/CC6.7
```

---

## 4. Simulate a GitHub PR webhook (full agent flow)

This triggers the Dev Team Agent end-to-end: clone → scan → brain lookup → Claude explanation → remediation PR.

```bash
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{
    "action": "opened",
    "pull_request": {
      "number": 42,
      "head": {
        "sha": "abc123",
        "repo": {"full_name": "your-org/your-repo"}
      }
    }
  }'
```

Watch the agent logs:

```bash
docker compose logs -f dev-team-agent
```

If violations are found, a PR will be opened on GitHub under branch `compliance-fix/<control_id>/<check_id>`.

---

Next: [How to Use →](how-to-use/README.md)
```

- [ ] **Step 2: Commit**

```bash
git add docs/gitbook/quick-start.md
git commit -m "docs: add GitBook quick start page"
```

---

### Task 11: Write docs/gitbook/how-to-use/README.md

**Files:**
- Create: `docs/gitbook/how-to-use/README.md`

- [ ] **Step 1: Write the file**

```markdown
# How to Use

ComplyAgent runs in two modes:

| Mode | When to use |
|------|-------------|
| **Event-driven** (production) | GitHub webhooks, Terraform CI, and the Kubernetes watcher publish events automatically. Agents consume them in real time. |
| **Manual** (development/testing) | Trigger scans directly via the FastAPI endpoints — no webhook setup needed. |

---

## What each agent watches

| Agent | Watches | SOC 2 controls |
|-------|---------|----------------|
| [Policy Agent](policy-agent.md) | Terraform plans, Kubernetes manifests | CC6.1, CC6.6, CC6.7, CC9.1 |
| [Cluster Operator Agent](cluster-operator-agent.md) | Live K8s state, Prometheus alerts | CC7.1, CC7.2, A1.1, CC6.8 |
| [Dev Team Agent](dev-team-agent.md) | GitHub pull requests | CC6.1, CC7.2, CC8.1, CC6.3 |

---

## The remediation loop

All three agents feed violations into the same [5-step remediation loop](remediation-loop.md):

```
NOTIFY → LEARN → RECOMMEND → MUTATE → VALIDATE
```

Every violation gets a Postgres evidence row, an LLM-generated explanation, and (where auto-remediation is supported) a GitHub PR — automatically.
```

- [ ] **Step 2: Commit**

```bash
git add docs/gitbook/how-to-use/README.md
git commit -m "docs: add GitBook how-to-use overview page"
```

---

### Task 12: Write docs/gitbook/how-to-use/policy-agent.md, cluster-operator-agent.md, dev-team-agent.md

**Files:**
- Create: `docs/gitbook/how-to-use/policy-agent.md`
- Create: `docs/gitbook/how-to-use/cluster-operator-agent.md`
- Create: `docs/gitbook/how-to-use/dev-team-agent.md`

- [ ] **Step 1: Write docs/gitbook/how-to-use/policy-agent.md**

```markdown
# Policy Agent

Watches Terraform plans and Kubernetes manifests for infrastructure governance violations using Checkov.

**Streams:** `tf.plans`, `k8s.events` | **Controls:** CC6.1, CC6.6, CC6.7, CC9.1

---

## Trigger manually

Publish a `tf.plans` event by posting a scan request:

```bash
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "infra/main.tf", "git_sha": "abc123"}'
```

---

## Example violation → remediation

An S3 bucket in `infra/main.tf` is missing server-side encryption:

1. Checkov returns `CKV2_AWS_61` → mapped to `CC6.7`
2. Claude explains: *"This S3 bucket stores sensitive data without encryption at rest, violating CC6.7..."*
3. PR opened on branch `compliance-fix/CC6.7/CKV2_AWS_61`
4. Checkov re-runs on the patched file → passes → evidence status set to `remediated`

---

## Add a new Checkov rule mapping

Open `scanners/checkov_runner.py` and add to `SOC2_CONTROL_MAP`:

```python
"CKV_AWS_XYZ": ("CC6.7", "Encryption at rest"),
```

No other files need to change.

→ [Full developer reference](../../agents/policy_agent.md)
```

- [ ] **Step 2: Write docs/gitbook/how-to-use/cluster-operator-agent.md**

```markdown
# Cluster Operator Agent

Watches live Kubernetes cluster state and Prometheus alerts for runtime violations that bypass GitOps.

**Streams:** `k8s.events`, `prometheus.alerts` | **Controls:** CC7.1, CC7.2, A1.1, CC6.8

---

## What makes it different

Checkov scans static IaC files. This agent watches what is *actually running*. A direct `kubectl edit` on a production resource never touches a file in Git — this agent catches it.

---

## Example violation → escalation

An engineer runs `kubectl edit deployment/api` and adds a `hostPath` volume mount:

1. Kubernetes watcher detects the change → `k8s.events` stream
2. Cluster Operator maps it to `CC6.6`
3. Claude explains the impact
4. Because this is a live cluster change (`scanner_used=k8s_watch`), a PR is **not** auto-opened
5. Slack alert sent to `#compliance-alerts` → human review required
6. Evidence status set to `escalated`

---

## Add a new Prometheus alert mapping

Open `agents/cluster_operator.py` and add a tuple to `_ALERT_CONTROL_MAP`:

```python
(
    ("diskencryption", "unencryptedvolume"),
    ("CC6.7", "Encryption at rest"),
),
```

→ [Full developer reference](../../agents/cluster_operator.md)
```

- [ ] **Step 3: Write docs/gitbook/how-to-use/dev-team-agent.md**

```markdown
# Dev Team Agent

Scans every pull request for secrets and code-level compliance violations.

**Stream:** `github.prs` | **Controls:** CC6.1, CC6.3, CC7.2, CC8.1

---

## Trigger manually

```bash
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{
    "action": "opened",
    "pull_request": {
      "number": 42,
      "head": {"sha": "abc123", "repo": {"full_name": "org/repo"}}
    }
  }'
```

---

## Scanner chain

1. **Trufflehog** — scans full git history of the PR branch for live secrets
2. **Semgrep** — runs custom rules from `semgrep_rules/` for code patterns

---

## Example violation → remediation

A new endpoint writes to the database without calling `audit_log()`:

1. Semgrep rule `audit_log.yaml` fires → `CC7.2`
2. Claude explains the audit trail gap
3. PR opened: `compliance-fix/CC7.2/semgrep-audit-log`
4. Semgrep re-runs → passes → status `remediated`

---

## Add a custom Semgrep rule

Create a `.yaml` file in `semgrep_rules/`:

```yaml
rules:
  - id: require-rate-limit-on-auth-endpoints
    patterns:
      - pattern: |
          @app.route("/login", ...)
          def $FUNC(...):
              ...
    message: "Auth endpoint missing rate limiting — CC6.2 violation"
    languages: [python]
    severity: WARNING
    metadata:
      control_id: CC6.2
      control_name: "Authentication and MFA"
```

→ [Full developer reference](../../agents/dev_team_agent.md)
```

- [ ] **Step 4: Commit**

```bash
git add docs/gitbook/how-to-use/policy-agent.md \
        docs/gitbook/how-to-use/cluster-operator-agent.md \
        docs/gitbook/how-to-use/dev-team-agent.md
git commit -m "docs: add GitBook agent how-to pages"
```

---

### Task 13: Write docs/gitbook/how-to-use/remediation-loop.md

**Files:**
- Create: `docs/gitbook/how-to-use/remediation-loop.md`

- [ ] **Step 1: Write the file**

```markdown
# Remediation Loop

Every agent feeds violations into the same 5-step loop. The loop lives in `agents/remediation.py` and is shared across all agents.

---

## The 5 steps

| Step | What happens |
|------|-------------|
| **1. NOTIFY** | Violation is logged to Postgres (`status=open`) — the permanent audit record |
| **2. LEARN** | Qdrant is queried for the exact SOC 2 Trust Service Criterion text matching the `control_id` |
| **3. RECOMMEND** | Claude generates a plain-English explanation: what's wrong, why it matters, how to fix it |
| **4. MUTATE** | The violating file is fetched from GitHub, patched by Claude, and a PR is opened on branch `compliance-fix/<control_id>/<check_id>` |
| **5. VALIDATE** | The original scanner re-runs on the patched file |

---

## Outcomes

| Outcome | Condition | Result |
|---------|-----------|--------|
| **REMEDIATED** | VALIDATE passes | Evidence status → `remediated`, PR URL logged |
| **ESCALATED** | VALIDATE fails, or `scanner_used=k8s_watch` | Evidence status → `escalated`, Slack alert sent |

---

## Evidence status lifecycle

```
open → remediated
     → escalated
     → false_positive  (manual update)
```

Evidence rows are never deleted. Status only moves forward.

---

## Branch and PR naming

- Branch: `compliance-fix/<control_id>/<check_id>`
  - Example: `compliance-fix/CC6.7/CKV2_AWS_61`
- PR title: `[<control_id>] Fix: <violation summary>`
  - Example: `[CC6.7] Fix: S3 encryption missing on app_data bucket`
- PR label: `compliance-fix`

→ [Full developer reference](../../remediation_loop.md)
```

- [ ] **Step 2: Commit**

```bash
git add docs/gitbook/how-to-use/remediation-loop.md
git commit -m "docs: add GitBook remediation loop page"
```

---

### Task 14: Write docs/gitbook/configuration.md

**Files:**
- Create: `docs/gitbook/configuration.md`

- [ ] **Step 1: Write the file**

```markdown
# Configuration

All configuration is via environment variables in `.env`. Copy `.env.example` to `.env` and fill in the values below.

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://complyagent:complyagentsecret@localhost:5432/compliance` | Postgres connection string |
| `REDIS_URL` | Yes | `redis://localhost:6379` | Redis connection string |
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key — get one at console.anthropic.com |
| `QDRANT_URL` | Yes | `http://localhost:6333` | Qdrant vector DB URL |
| `GITHUB_TOKEN` | Yes | — | GitHub PAT with `repo` scope (read + write) |
| `GITHUB_REPO_OWNER` | Yes | — | GitHub org or user owning the target repo |
| `GITHUB_REPO_NAME` | Yes | — | Target repository name (without owner prefix) |
| `GITHUB_WEBHOOK_SECRET` | No | `""` | HMAC secret for GitHub webhook signature verification. If unset, signature check is skipped. |
| `SLACK_BOT_TOKEN` | No | — | Slack bot token (`xoxb-...`) for escalation alerts |
| `SLACK_ALERT_CHANNEL` | No | `#compliance-alerts` | Slack channel where escalation alerts are posted |
| `CLONE_DEPTH` | No | `1` | Git clone depth for PR scanning. Increase if Trufflehog needs deeper history. |

---

## GitHub webhook setup (for production)

To receive live GitHub events, expose your FastAPI server and register the webhook:

1. Expose locally with ngrok for testing:
   ```bash
   ngrok http 8000
   ```

2. In your GitHub repo → Settings → Webhooks → Add webhook:
   - **Payload URL:** `https://<your-ngrok-url>/webhook/github`
   - **Content type:** `application/json`
   - **Secret:** value of `GITHUB_WEBHOOK_SECRET`
   - **Events:** Pull requests, Pushes

---

## Slack escalation setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
2. Add **OAuth scope:** `chat:write`
3. Install the app to your workspace
4. Copy the **Bot User OAuth Token** (`xoxb-...`) to `SLACK_BOT_TOKEN`
5. Invite the bot to your alert channel: `/invite @your-bot-name`
6. Set `SLACK_ALERT_CHANNEL=#your-channel`

---

## Qdrant

No additional configuration beyond `QDRANT_URL`. SOC 2 Trust Service Criteria embeddings are loaded into Qdrant automatically at startup via `brain/embeddings.py`. The collection is created if it doesn't exist.
```

- [ ] **Step 2: Commit**

```bash
git add docs/gitbook/configuration.md
git commit -m "docs: add GitBook configuration reference page"
```

---

### Task 15: Write docs/gitbook/troubleshooting.md

**Files:**
- Create: `docs/gitbook/troubleshooting.md`

- [ ] **Step 1: Write the file**

```markdown
# Troubleshooting

---

## Common errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| `RuntimeError: checkov binary not found` | Checkov not on PATH | `pip install checkov` |
| `asyncpg.exceptions.ConnectionDoesNotExistError` | Postgres not running | `docker compose up postgres` |
| `redis.exceptions.ConnectionError` | Redis not running | `docker compose up redis` |
| `ConnectionRefusedError` on Qdrant | Qdrant not running | `docker compose up qdrant` |
| Agent starts but no findings logged | `GITHUB_TOKEN` missing or wrong scope | Token needs `repo` scope (read + write) |
| Remediation PR not opened | Target repo write access missing | Ensure `GITHUB_TOKEN` has write access to `GITHUB_REPO_OWNER/GITHUB_REPO_NAME` |
| Slack alerts not firing | `SLACK_BOT_TOKEN` not set | Add to `.env` and `docker compose restart` |
| `asyncio.TimeoutError` on Checkov scan | Large file or slow system | Pass `timeout=300` to `CheckovRunner.scan()` |
| GitBook shows blank pages | `SUMMARY.md` path mismatch | Ensure all paths in `SUMMARY.md` are relative to `docs/gitbook/` |

---

## Inspect evidence

```bash
# Via API
curl http://localhost:8000/evidence
curl http://localhost:8000/evidence/CC6.7

# Via Postgres directly
docker compose exec postgres psql -U complyagent -d compliance \
  -c "SELECT check_id, control_id, status, created_at FROM evidence_events ORDER BY created_at DESC LIMIT 20;"
```

---

## Read agent logs

```bash
# All services
docker compose logs -f

# Single agent
docker compose logs -f dev-team-agent
docker compose logs -f policy-agent
docker compose logs -f cluster-operator
```

---

## Reset the evidence store

```bash
docker compose exec postgres psql -U complyagent -d compliance \
  -c "TRUNCATE evidence_events;"
```

---

## Re-seed Qdrant embeddings

If the Qdrant collection is empty or corrupt:

```bash
docker compose exec api python -c "
import asyncio
from brain.embeddings import seed_embeddings
asyncio.run(seed_embeddings())
"
```

---

## Run tests locally

```bash
pip install -r requirements.txt checkov
pytest tests/ -v
```

Individual test files:

```bash
pytest tests/test_checkov_runner.py -v
pytest tests/test_policy_agent.py -v
pytest tests/test_remediation_loop.py -v
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/gitbook/troubleshooting.md
git commit -m "docs: add GitBook troubleshooting page"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Covered by |
|-----------------|-----------|
| README: replace 6-week table with feature matrix | Task 1 |
| README: add "How to use" section (4 sub-sections) | Task 1 |
| README: update project structure tree | Task 1 |
| README: update tech stack table | Task 1 |
| docs/index.md: full system data flow | Task 2 |
| docs/index.md: updated module map (13 rows) | Task 2 |
| docs/agents/policy_agent.md | Task 3 |
| docs/agents/cluster_operator.md | Task 4 |
| docs/agents/dev_team_agent.md | Task 5 |
| docs/remediation_loop.md | Task 6 |
| docs/gitbook/SUMMARY.md | Task 7 |
| docs/gitbook/introduction.md | Task 8 |
| docs/gitbook/installation.md | Task 9 |
| docs/gitbook/quick-start.md | Task 10 |
| docs/gitbook/how-to-use/README.md | Task 11 |
| docs/gitbook/how-to-use/policy-agent.md | Task 12 |
| docs/gitbook/how-to-use/cluster-operator-agent.md | Task 12 |
| docs/gitbook/how-to-use/dev-team-agent.md | Task 12 |
| docs/gitbook/how-to-use/remediation-loop.md | Task 13 |
| docs/gitbook/configuration.md | Task 14 |
| docs/gitbook/troubleshooting.md | Task 15 |

All 21 spec requirements covered. ✅

### Key accuracy notes

- `SLACK_BOT_TOKEN` + `SLACK_ALERT_CHANNEL` (not `SLACK_WEBHOOK_URL`) — matches `notify/slack.py`
- `ClusterOperatorAgent.STREAMS = ["k8s.events", "prometheus.alerts"]` — matches source
- `k8s_watch` findings skip MUTATE (not in `_VALIDATE_SUPPORTED`) — matches `agents/remediation.py`
- Branch naming `compliance-fix/<control_id>/<check_id>` — matches `AGENTS.md`
- `claude-sonnet-4-6` — correct current model ID
