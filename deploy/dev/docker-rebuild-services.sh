#!/usr/bin/env bash
# Pull the latest dependency images (asr-webservice x2, ollama) and recreate
# their containers. Run after bumping ASR_IMAGE / ollama tags or to refresh
# the external services stack.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --env-file is optional here (HF_TOKEN / ASR_IMAGE overrides live in it); the
# compose file has working defaults without it.
ENV_ARGS=()
[[ -f "$SCRIPT_DIR/.env" ]] && ENV_ARGS=(--env-file "$SCRIPT_DIR/.env")

docker compose -f "$SCRIPT_DIR/docker-compose.services.yml" "${ENV_ARGS[@]}" pull
docker compose -f "$SCRIPT_DIR/docker-compose.services.yml" "${ENV_ARGS[@]}" up -d
echo "External services pulled and recreated (asr-webservice :9000, asr-webservice2 :9001, ollama :11434)."
