#!/usr/bin/env bash
# Rebuild the asr-crawler app image and restart its container.
# Run after changing src/ or pyproject.toml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" --env-file "$SCRIPT_DIR/.env" up -d --build asr-crawler
echo "asr-crawler image rebuilt and container restarted."
