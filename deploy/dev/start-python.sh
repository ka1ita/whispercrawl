#!/usr/bin/env bash
# Start whisper-asr-webservice + Ollama in Docker, then run WhisperCrawl locally via Python.
# Services are exposed on localhost so config.yaml defaults (localhost:9000 / localhost:11434) work as-is.
#
# Usage:
#   ./deploy/dev/start-python.sh              # run on schedule (default)
#   ./deploy/dev/start-python.sh --once       # single pass
#   ./deploy/dev/start-python.sh --once --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

#docker compose -f "$SCRIPT_DIR/docker-compose.services.yml" up -d
#echo "Services started (whisper :9000, ollama :11434)."
#echo ""

cd "$REPO_ROOT"
exec python -m whispercrawl --config config.yaml "$@"
