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
