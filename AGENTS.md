# AGENTS.md — Agent Roster & Communication Contract

This document is the source-of-truth for every autonomous agent in the
SOC 2 Compliance Automation system.  It defines each agent's identity,
scope, event subscriptions, and the shared contracts that let agents
communicate without knowing about each other.

---

## Architecture principle

Each agent is a **narrow, single-domain expert**.  Agents do not call each
other directly — they communicate exclusively through named Redis Streams.
Adding a new agent requires zero changes to existing code.

```
Sources                    Redis Streams             Agents
──────────────────────     ─────────────────         ─────────────────────
GitHub push/PR         →   github.prs          →     Dev Team Agent
Terraform plan         →   tf.plans            →     Policy Agent
Kubernetes watch       →   k8s.events          →  ┬  Policy Agent
                                                   └  Cluster Operator Agent
Prometheus alert       →   prometheus.alerts   →     (future: Availability Agent)
```

---

## Agent 1 — Policy Agent

| Property       | Value |
|----------------|-------|
| **Module**     | `agents/policy_agent.py` |
| **Streams**    | `k8s.events`, `tf.plans` |
| **Scanners**   | Checkov |
| **Controls**   | CC6.1, CC6.6, CC6.7, CC9.1 |

**Purpose:** Watches governance rules across all infrastructure.  Every
Terraform plan is scanned for misconfigured resources (wrong encryption,
wildcard IAM policies, unrotated keys).  Kubernetes manifests are checked
for security policy violations before they reach the cluster.

**Example violation:** A Terraform plan adding an S3 bucket without
`server_side_encryption_configuration` → CC6.7 violation → PR opens that
adds the `aws_s3_bucket_server_side_encryption_configuration` resource.

---

## Agent 2 — Cluster Operator Agent

| Property       | Value |
|----------------|-------|
| **Module**     | `agents/cluster_operator.py` |
| **Streams**    | `k8s.events` |
| **Scanners**   | kubernetes-asyncio watch API |
| **Controls**   | CC7.1, CC7.2, A1.1, CC6.8 |

**Purpose:** Watches *live* Kubernetes cluster state for drift — resources
that have diverged from their Git-committed definition.  The key signal this
agent catches that others can't: a `kubectl edit` on a production Pod that
bypasses the GitOps pipeline entirely.

**Example violation:** Someone directly patches `deployment/api` to add an
`emptyDir` hostPath volume mount → CC6.6 violation → Slack alert + PR to
remove the mount from the Helm values file.

---

## Agent 3 — Dev Team Agent

| Property       | Value |
|----------------|-------|
| **Module**     | `agents/dev_team_agent.py` |
| **Streams**    | `github.prs` |
| **Scanners**   | Trufflehog, Semgrep |
| **Controls**   | CC6.1, CC7.2, CC8.1, CC6.3 |

**Purpose:** Watches every pull request for code-level compliance violations.
Trufflehog scans the full git history of every PR branch for live secrets.
Semgrep uses custom rules to enforce code patterns (e.g., every data-write
function must call `audit_log()`).

**Example violation:** New `/api/users` POST endpoint writes to the database
but never calls `audit_log()` → CC7.2 violation → PR comment + remediation
PR adding the missing audit call.

---

## The 5-Step Remediation Loop

Every agent runs this loop on every violation it finds:

```
1. NOTIFY    → publish violation event to Redis Streams
2. LEARN     → query Qdrant RAG for the exact SOC 2 control text
3. RECOMMEND → Claude generates plain-English explanation + specific fix
4. MUTATE    → fetch file from GitHub, patch it via LLM, open PR
                  branch: compliance-fix/<control_id>/<check_id>
                  title:  "[CC6.7] Fix: S3 encryption missing on app_data bucket"
                  labels: ["compliance-fix"]
5. VALIDATE  → re-run scanner on patched file
               → PASS: log REMEDIATED to evidence store
               → FAIL: escalate to Slack, flag for human review
```

---

## Event Schema (Redis Streams)

All events on all streams share this base envelope:

```json
{
  "event_id":    "uuid-v4",
  "timestamp":   "2026-05-27T10:00:00Z",
  "source":      "checkov | trufflehog | semgrep | k8s_watch",
  "agent":       "policy | cluster_operator | dev_team",
  "check_id":    "CKV_AWS_19",
  "control_id":  "CC6.7",
  "resource":    "aws_s3_bucket.app_data",
  "file_path":   "infra/main.tf",
  "git_sha":     "abc123def",
  "severity":    "HIGH",
  "payload":     { /* raw scanner JSON */ }
}
```

---

## Shared Infrastructure

| Component     | Purpose                                      | Used by       |
|---------------|----------------------------------------------|---------------|
| Claude API    | Explanation + fix generation (structured JSON) | All agents  |
| Qdrant        | SOC 2 control text retrieval (RAG)            | All agents    |
| Redis Streams | Event bus — decoupled pub/sub                 | All agents    |
| Postgres      | Evidence store — immutable audit trail        | All agents    |
| GitHub API    | File fetch + PR creation                      | All agents    |
