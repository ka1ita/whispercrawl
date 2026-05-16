#!/usr/bin/env bash
# Start the full dev stack: whisper, ollama, and WhisperCrawl  — all in Docker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" --env-file "$SCRIPT_DIR/.env" up -d
echo "Dev stack started. Tail logs with:"
echo "  docker compose -f $SCRIPT_DIR/docker-compose.dev.yml logs -f"
