#!/usr/bin/env bash
# Stop whisper-asr-webservice and Ollama (external services only).
# For the full dev stack (docker-compose.dev.yml) use app-docker-stop.sh instead.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ENV_ARGS=()
[[ -f "$SCRIPT_DIR/.env" ]] && ENV_ARGS=(--env-file "$SCRIPT_DIR/.env")

docker compose -f "$SCRIPT_DIR/docker-compose.services.yml" "${ENV_ARGS[@]}" down
echo "External services stopped (whisper, whisper2, ollama)."
