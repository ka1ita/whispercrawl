#!/usr/bin/env bash
# Restart whisper-asr-webservice and Ollama (external services only).
# Use this when running WhisperCrawl locally (not in Docker).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --env-file is optional here (HF_TOKEN / ASR_IMAGE overrides live in it); the
# compose file has working defaults without it.
ENV_ARGS=()
[[ -f "$SCRIPT_DIR/.env" ]] && ENV_ARGS=(--env-file "$SCRIPT_DIR/.env")

docker compose -f "$SCRIPT_DIR/docker-compose.services.yml" "${ENV_ARGS[@]}" restart
echo "External services restarted (asr-webservice :9000, asr-webservice2 :9001, ollama :11434)."
