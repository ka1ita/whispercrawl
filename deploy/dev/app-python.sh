#!/usr/bin/env bash
# Run asr-crawler locally via Python against the dev two-engine config.
# Start the ASR services first: ./deploy/dev/services-docker-start.sh
#   (asr-webservice :9000 and asr-webservice2 :9001, ollama :11434 — all on localhost, so the
#    deploy/dev/config.yaml URL defaults work as-is).
#
# Usage:
#   ./deploy/dev/app-python.sh              # run on schedule (default)
#   ./deploy/dev/app-python.sh --once       # single pass
#   ./deploy/dev/app-python.sh --once --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

#docker compose -f "$SCRIPT_DIR/docker-compose.services.yml" up -d
#echo "Services started (asr-webservice :9000, asr-webservice2 :9001, ollama :11434)."
#echo ""

cd "$REPO_ROOT"
exec python -m asr_crawler --config deploy/dev/config.yaml "$@"
