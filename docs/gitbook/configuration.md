# Configuration

All configuration is via environment variables in `.env`. Copy `.env.example` to `.env` and fill in the values below.

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://complyagent:complyagentsecret@localhost:5432/compliance` | Postgres connection string |
| `REDIS_URL` | Yes | `redis://localhost:6379` | Redis connection string |
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key — get one at console.anthropic.com |
| `QDRANT_URL` | Yes | `http://localhost:6333` | Qdrant vector DB URL |
| `GITHUB_TOKEN` | Yes | — | GitHub PAT with `repo` scope (read + write) |
| `GITHUB_REPO_OWNER` | Yes | — | GitHub org or user owning the target repo |
| `GITHUB_REPO_NAME` | Yes | — | Target repository name (without owner prefix) |
| `GITHUB_WEBHOOK_SECRET` | No | `""` | HMAC secret for GitHub webhook signature verification. If unset, signature check is skipped. |
| `SLACK_BOT_TOKEN` | No | — | Slack bot token (`xoxb-...`) for escalation alerts |
| `SLACK_ALERT_CHANNEL` | No | `#compliance-alerts` | Slack channel where escalation alerts are posted |
| `CLONE_DEPTH` | No | `1` | Git clone depth for PR scanning. Increase if Trufflehog needs deeper history. |

---

## GitHub webhook setup (for production)

To receive live GitHub events, expose your FastAPI server and register the webhook:

1. Expose locally with ngrok for testing:
   ```bash
   ngrok http 8000
   ```

2. In your GitHub repo → Settings → Webhooks → Add webhook:
   - **Payload URL:** `https://<your-ngrok-url>/webhook/github`
   - **Content type:** `application/json`
   - **Secret:** value of `GITHUB_WEBHOOK_SECRET`
   - **Events:** Pull requests, Pushes

---

## Slack escalation setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
2. Add **OAuth scope:** `chat:write`
3. Install the app to your workspace
4. Copy the **Bot User OAuth Token** (`xoxb-...`) to `SLACK_BOT_TOKEN`
5. Invite the bot to your alert channel: `/invite @your-bot-name`
6. Set `SLACK_ALERT_CHANNEL=#your-channel`

---

## Qdrant

No additional configuration beyond `QDRANT_URL`. SOC 2 Trust Service Criteria embeddings are loaded into Qdrant automatically at startup via `brain/embeddings.py`. The collection is created if it doesn't exist.
