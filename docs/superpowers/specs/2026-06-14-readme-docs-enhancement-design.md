# README & Docs Enhancement — Design Spec

**Date:** 2026-06-14
**Author:** anwer
**Status:** Approved

---

## Goal

Bring the README and developer docs up to date with the fully-implemented system, and add targeted onboarding docs for the three agents and remediation loop. Primary audience: developers joining the project.

---

## Approach

**README-first, docs as satellites.** The README is the authoritative first read. Four new satellite docs give agents and the remediation loop their own space. No new tooling required.

---

## Files Affected

| File | Action |
|------|--------|
| `README.md` | Rewrite (structure preserved, content updated) |
| `docs/index.md` | Update to reflect full system |
| `docs/agents/policy_agent.md` | Create |
| `docs/agents/cluster_operator.md` | Create |
| `docs/agents/dev_team_agent.md` | Create |
| `docs/remediation_loop.md` | Create |

---

## Section 1 — README.md

### 1.1 Header
- Project name + CI badge
- One-sentence description

### 1.2 Why this exists
- Keep current text, trim to 3 bullet points

### 1.3 Architecture overview
- Keep existing ASCII diagram
- Update tech stack table (correct Claude model ID: `claude-sonnet-4-6`)

### 1.4 What's implemented *(replaces 6-week build plan)*
Matrix with columns: `Capability | Module | Status | Doc`

Rows:
1. Webhook server — `api/webhooks.py` — ✅ — `docs/webhooks.md`
2. Checkov runner — `scanners/checkov_runner.py` — ✅ — `docs/checkov_runner.md`
3. Evidence store — `store/` — ✅ — `docs/evidence_store.md`
4. Redis event bus — `agents/base_agent.py` — ✅ — `AGENTS.md`
5. Compliance brain (RAG) — `brain/` — ✅ — `AGENTS.md`
6. Policy Agent — `agents/policy_agent.py` — ✅ — `docs/agents/policy_agent.md`
7. Cluster Operator Agent — `agents/cluster_operator.py` — ✅ — `docs/agents/cluster_operator.md`
8. Dev Team Agent — `agents/dev_team_agent.py` — ✅ — `docs/agents/dev_team_agent.md`
9. Remediation loop — `mutate/`, `notify/` — ✅ — `docs/remediation_loop.md`
10. Dashboard — `dashboard/` — ✅ — —

### 1.5 SOC 2 control coverage
Keep existing table — it's accurate.

### 1.6 How to use *(new)*
Four sub-sections:

**Start the stack**
```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET
docker compose up --build
```
Services: FastAPI (8000), Qdrant (6333), Redis (6379), Postgres (5432), Dashboard (5173)

**Trigger a scan manually**
```bash
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "tests/fixtures/demo.tf", "git_sha": "abc123"}'
```
Expected: list of `CheckovFinding` objects with `check_id`, `control_id`, `severity`.

**Simulate a GitHub PR webhook (end-to-end agent flow)**
```bash
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{"action": "opened", "pull_request": {"number": 42, "head": {"sha": "abc123", "repo": {"full_name": "org/repo"}}}}'
```
This triggers the Dev Team Agent: Trufflehog + Semgrep scan → brain RAG lookup → Claude explanation → remediation PR if violations found.

**Query evidence**
```bash
curl http://localhost:8000/evidence           # all recent findings
curl http://localhost:8000/evidence/CC6.7     # filter by SOC 2 control
```

### 1.7 Local development
- Prerequisites: Python 3.12, `pip install -r requirements.txt checkov`
- Run tests: `pytest tests/ -v`
- Full env vars reference table (DATABASE_URL, REDIS_URL, ANTHROPIC_API_KEY, QDRANT_URL, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET)

### 1.8 Project structure
Updated file tree reflecting current layout including `notify/`, corrected `dashboard/`, `agents/remediation.py`.

---

## Section 2 — New Agent Docs

### 2.1 `docs/agents/policy_agent.md`
- **Purpose:** Terraform + Kubernetes governance via Checkov
- **Streams:** `tf.plans`, `k8s.events`
- **LangGraph steps:** scan → map_to_control → brain_lookup → recommend → mutate
- **Example:** S3 bucket without `server_side_encryption_configuration` → CC6.7 → PR opens
- **Extend:** How to add a Checkov rule to `SOC2_CONTROL_MAP`

### 2.2 `docs/agents/cluster_operator.md`
- **Purpose:** Live Kubernetes drift detection via kubernetes-asyncio watch API
- **Streams:** `k8s.events`
- **What it catches vs Checkov:** Checkov catches static manifests; this catches live runtime state that bypasses GitOps
- **Example:** Direct `kubectl edit` on production Pod → CC6.6 → Slack alert + PR to Helm values
- **LangGraph steps:** watch_event → detect_drift → brain_lookup → recommend → mutate

### 2.3 `docs/agents/dev_team_agent.md`
- **Purpose:** PR-level secret and SAST scanning
- **Streams:** `github.prs`
- **Scanner chain:** Trufflehog (full branch history) → Semgrep (custom rules in `semgrep_rules/`)
- **Example:** New endpoint writes to DB without `audit_log()` → CC7.2 → PR comment + remediation PR
- **Extend:** How to add a custom Semgrep rule in `semgrep_rules/`

### 2.4 `docs/remediation_loop.md`
- **The 5 steps:** NOTIFY → LEARN → RECOMMEND → MUTATE → VALIDATE
- **Branch naming:** `compliance-fix/<control_id>/<check_id>`
- **VALIDATE outcomes:** PASS → log `REMEDIATED` to evidence store; FAIL → escalate to Slack, flag `escalated`
- **Evidence status transitions:** `open → remediated | escalated | false_positive`
- **Sequence diagram:** full flow from violation detection to PR merge

---

## Section 3 — `docs/index.md` Update

- Replace Week 1 data flow with full system flow (all 3 agents, brain, remediation loop)
- Updated module map table: all current modules, not just Week 1
- Navigation links to all satellite docs

---

## Out of Scope

- `brain/` internals (embeddings, RAG pipeline) — not in this spec
- `dashboard/` internals — not in this spec
- Adding new MkDocs/static site tooling
- Any code changes — documentation only
