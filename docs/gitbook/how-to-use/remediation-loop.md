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
