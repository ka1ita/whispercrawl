#!/usr/bin/env bash
# Rebuild the WhisperCrawl Docker image and restart its container.
# Run after changing src/ or pyproject.toml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" --env-file "$REPO_ROOT/.env" up -d --build whispercrawl
echo "whispercrawl image rebuilt and container restarted."
