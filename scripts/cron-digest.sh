#!/usr/bin/env bash
#
# Cron entry point for the server. Runs one digest, then exits.
# The rsshub service is expected to be already running (docker compose up -d rsshub);
# `docker compose run` starts it on demand anyway and waits for it to be healthy.
#
# Install (run daily at 06:00 Europe/Moscow = 03:00 UTC):
#   crontab -e
#   0 3 * * *  /opt/news_digets/scripts/cron-digest.sh >> /var/log/news-digest.log 2>&1
#
# Override the config with the first argument (defaults to torchlab-ai):
#   ./scripts/cron-digest.sh torchlab-ai

set -euo pipefail

# Resolve the project root from this script's location so cron's cwd doesn't matter.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

CONFIG_NAME="${1:-torchlab-ai}"

# Prefer the Compose V2 plugin; fall back to the legacy binary if present.
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
else
  COMPOSE="docker-compose"
fi

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] starting digest: ${CONFIG_NAME}"

# Make sure RSSHub is up (idempotent), then run the one-shot job.
$COMPOSE up -d rsshub
$COMPOSE run --rm digest --config "configs/${CONFIG_NAME}.yml"

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] digest finished: ${CONFIG_NAME}"
