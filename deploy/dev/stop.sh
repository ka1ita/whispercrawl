#!/usr/bin/env bash
# Stop the full dev stack (docker-compose.dev.yml).
# If you started only the external services via start-services.sh, use:
#   bash start-services.sh down   (or: docker compose -f deploy/dev/docker-compose.services.yml down)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" --env-file "$SCRIPT_DIR/.env" down
