FROM python:3.12-slim

# git for repo clones; build-essential for native wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Scanners called as subprocesses by the agents
RUN pip install --no-cache-dir checkov semgrep \
    && curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh \
       | sh -s -- -b /usr/local/bin

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.webhooks:app", "--host", "0.0.0.0", "--port", "8000"]
