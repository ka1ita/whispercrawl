#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

docker compose -f docker-compose.prod.yml up -d
echo "Service started. Tail logs with:  docker compose -f docker-compose.prod.yml logs -f"
