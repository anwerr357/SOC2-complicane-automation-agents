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
