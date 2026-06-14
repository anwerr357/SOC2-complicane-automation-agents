# Policy Agent

Watches Terraform plans and Kubernetes manifests for infrastructure governance violations using Checkov.

**Streams:** `tf.plans`, `k8s.events` | **Controls:** CC6.1, CC6.6, CC6.7, CC9.1

***

## Trigger manually

Publish a `tf.plans` event by posting a scan request:

```bash
curl -X POST http://localhost:8000/scan/checkov \
  -H "Content-Type: application/json" \
  -d '{"file_path": "infra/main.tf", "git_sha": "abc123"}'
```

***

## Example violation → remediation

An S3 bucket in `infra/main.tf` is missing server-side encryption:

1. Checkov returns `CKV2_AWS_61` → mapped to `CC6.7`
2. Claude explains: _"This S3 bucket stores sensitive data without encryption at rest, violating CC6.7..."_
3. PR opened on branch `compliance-fix/CC6.7/CKV2_AWS_61`
4. Checkov re-runs on the patched file → passes → evidence status set to `remediated`

***

## Add a new Checkov rule mapping

Open `scanners/checkov_runner.py` and add to `SOC2_CONTROL_MAP`:

```python
"CKV_AWS_XYZ": ("CC6.7", "Encryption at rest"),
```
