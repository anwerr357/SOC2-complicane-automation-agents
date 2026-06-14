# Troubleshooting

---

## Common errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| `RuntimeError: checkov binary not found` | Checkov not on PATH | `pip install checkov` |
| `asyncpg.exceptions.ConnectionDoesNotExistError` | Postgres not running | `docker compose up postgres` |
| `redis.exceptions.ConnectionError` | Redis not running | `docker compose up redis` |
| `ConnectionRefusedError` on Qdrant | Qdrant not running | `docker compose up qdrant` |
| Agent starts but no findings logged | `GITHUB_TOKEN` missing or wrong scope | Token needs `repo` scope (read + write) |
| Remediation PR not opened | Target repo write access missing | Ensure `GITHUB_TOKEN` has write access to `GITHUB_REPO_OWNER/GITHUB_REPO_NAME` |
| Slack alerts not firing | `SLACK_BOT_TOKEN` not set | Add to `.env` and `docker compose restart` |
| `asyncio.TimeoutError` on Checkov scan | Large file or slow system | Pass `timeout=300` to `CheckovRunner.scan()` |
| GitBook shows blank pages | `SUMMARY.md` path mismatch | Ensure all paths in `SUMMARY.md` are relative to `docs/gitbook/` |

---

## Inspect evidence

```bash
# Via API
curl http://localhost:8000/evidence
curl http://localhost:8000/evidence/CC6.7

# Via Postgres directly
docker compose exec postgres psql -U complyagent -d compliance \
  -c "SELECT check_id, control_id, status, created_at FROM evidence_events ORDER BY created_at DESC LIMIT 20;"
```

---

## Read agent logs

```bash
# All services
docker compose logs -f

# Single agent
docker compose logs -f dev-team-agent
docker compose logs -f policy-agent
docker compose logs -f cluster-operator
```

---

## Reset the evidence store

```bash
docker compose exec postgres psql -U complyagent -d compliance \
  -c "TRUNCATE evidence_events;"
```

---

## Re-seed Qdrant embeddings

If the Qdrant collection is empty or corrupt:

```bash
docker compose exec api python -c "
import asyncio
from brain.embeddings import seed_embeddings
asyncio.run(seed_embeddings())
"
```

---

## Run tests locally

```bash
pip install -r requirements.txt checkov
pytest tests/ -v
```

Individual test files:

```bash
pytest tests/test_checkov_runner.py -v
pytest tests/test_policy_agent.py -v
pytest tests/test_remediation_loop.py -v
```
