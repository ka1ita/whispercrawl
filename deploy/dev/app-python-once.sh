#!/usr/bin/env bash
# Run asr-crawler locally via Python against the dev two-engine config — single pass, then exit.
# Start the ASR services first: ./deploy/dev/services-docker-start.sh (asr-webservice :9000, asr-webservice2 :9001).
#
# Usage:
#   ./deploy/dev/app-python-once.sh
#   ./deploy/dev/app-python-once.sh --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"
exec python -m asr_crawler --config deploy/dev/config.yaml --once "$@"
