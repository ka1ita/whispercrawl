#!/usr/bin/env bash
# Start the full dev stack: asr-webservice, ollama, and WhisperCrawl  — all in Docker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" --env-file "$SCRIPT_DIR/.env" up -d
echo "Dev stack started (asr-webservice :9000, asr-webservice2 :9001, ollama :11434; two ASR engines per EPIC-054)."
echo "Tail logs with:"
echo "  docker compose -f $SCRIPT_DIR/docker-compose.dev.yml logs -f"
