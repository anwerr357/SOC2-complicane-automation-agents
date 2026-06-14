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
