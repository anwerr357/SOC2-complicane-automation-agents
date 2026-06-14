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
