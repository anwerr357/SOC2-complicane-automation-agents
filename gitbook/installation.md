# Installation

---

## Prerequisites

- **Docker** + **Docker Compose v2** — all services run in containers
- **Python 3.12** — only needed for running tests locally without Docker
- **Checkov** — only needed for local test runs: `pip install checkov`

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/your-org/complianceAgents.git
cd complianceAgents
```

---

## Step 2 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
GITHUB_REPO_OWNER=your-org
GITHUB_REPO_NAME=your-repo

# Optional — needed for Slack escalation alerts
SLACK_BOT_TOKEN=xoxb-...
SLACK_ALERT_CHANNEL=#compliance-alerts
```

See [Configuration](configuration.md) for the full variable reference.

---

## Step 3 — Start the stack

```bash
docker compose up --build
```

First run takes ~3 minutes to pull images and build the Python container.

---

## Services

| Service | URL | Description |
|---------|-----|-------------|
| FastAPI | http://localhost:8000 | Main API — webhooks, scan triggers, evidence read |
| API docs | http://localhost:8000/docs | Swagger UI |
| Qdrant | http://localhost:6333/dashboard | Vector DB dashboard |
| Redis | localhost:6379 | Event bus (no UI) |
| Postgres | localhost:5432 | Evidence store (no UI) |
| Dashboard | http://localhost:5173 | React compliance dashboard |

---

## Verify the installation

```bash
curl http://localhost:8000/healthz
# → {"status": "ok"}
```

---

Next: [Quick Start →](quick-start.md)
