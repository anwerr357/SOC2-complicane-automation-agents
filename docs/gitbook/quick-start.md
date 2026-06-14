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
