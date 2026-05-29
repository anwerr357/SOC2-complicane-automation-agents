FROM python:3.12-slim

# ── System dependencies ────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Checkov (IaC scanner) ──────────────────────────────────────────────────
# Installed globally so the subprocess runner can call it directly
RUN pip install --no-cache-dir checkov

WORKDIR /app

# ── Python dependencies ────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ───────────────────────────────────────────────────────
COPY . .

# Expose FastAPI port
EXPOSE 8000

CMD ["uvicorn", "api.webhooks:app", "--host", "0.0.0.0", "--port", "8000"]
