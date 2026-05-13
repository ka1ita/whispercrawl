#!/usr/bin/env bash
# Run WhisperCrawl locally via Python — single pass, then exit.
#
# Usage:
#   ./deploy/dev/start-python-once.sh
#   ./deploy/dev/start-python-once.sh --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"
exec python -m whispercrawl --config config.yaml --once "$@"
