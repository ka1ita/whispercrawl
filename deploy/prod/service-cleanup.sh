#!/usr/bin/env bash
# Delete pipeline output files under watch_dir without running the pipeline.
#
# Usage:
#   ./service-cleanup.sh
#   ./service-cleanup.sh --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

docker compose -f docker-compose.prod.yml run --rm asr-crawler --once --cleanup "$@"
