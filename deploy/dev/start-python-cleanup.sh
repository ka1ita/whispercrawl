#!/usr/bin/env bash
# Delete pipeline output files under watch_dir without running the pipeline.
#
# Usage:
#   ./deploy/dev/start-python-cleanup.sh
#   ./deploy/dev/start-python-cleanup.sh --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"
exec python -m whispercrawl --config config.yaml --cleanup "$@"
