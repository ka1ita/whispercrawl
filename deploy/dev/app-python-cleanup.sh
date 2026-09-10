#!/usr/bin/env bash
# Delete pipeline output files under watch_dir without running the pipeline.
#
# Usage:
#   ./deploy/dev/app-python-cleanup.sh
#   ./deploy/dev/app-python-cleanup.sh --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
UV_BIN="$(command -v uv || true)"
[ -z "$UV_BIN" ] && [ -x "$HOME/.local/bin/uv" ] && UV_BIN="$HOME/.local/bin/uv"
if [ -n "$UV_BIN" ]; then
  exec "$UV_BIN" run --no-sync python -m asr_crawler --config deploy/dev/config.yaml --cleanup "$@"
else
  exec python -m asr_crawler --config deploy/dev/config.yaml --cleanup "$@"
fi
