#!/usr/bin/env bash
# Run WhisperCrawl locally via Python against the dev two-engine config — single pass, then exit.
# Start the ASR services first: ./deploy/dev/services-docker-start.sh (whisper :9000, whisper2 :9001).
#
# Usage:
#   ./deploy/dev/app-python-once.sh
#   ./deploy/dev/app-python-once.sh --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"
exec python -m whispercrawl --config deploy/dev/config.yaml --once "$@"
