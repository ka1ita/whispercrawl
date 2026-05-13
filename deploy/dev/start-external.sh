#!/usr/bin/env bash
# Start whisper-asr-webservice and Ollama only.
# Use this when running WhisperCrawl  locally (not in Docker).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

docker compose -f "$SCRIPT_DIR/docker-compose.services.yml" up -d
echo "External services started (whisper :9000, ollama :11434)."
echo "Pull a model if needed:"
echo "  docker compose -f $SCRIPT_DIR/docker-compose.services.yml exec ollama ollama pull gemma3:1b"
