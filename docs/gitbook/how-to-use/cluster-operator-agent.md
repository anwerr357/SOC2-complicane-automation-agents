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
