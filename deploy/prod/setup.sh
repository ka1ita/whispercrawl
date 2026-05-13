#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Creating runtime directories ..."
mkdir -p audio logs

echo "==> Loading whispercrawl Docker image ..."
if [[ ! -f dist/whispercrawl.tar ]]; then
  echo "ERROR: dist/whispercrawl.tar not found." >&2
  echo "       Transfer it to this directory before running setup." >&2
  exit 1
fi
docker load -i dist/whispercrawl.tar

echo ""
echo "Setup complete. Next steps:"
echo ""
echo "  1. cp .env.example .env"
echo "     Edit .env — set WHISPER_URL and OLLAMA_URL to your service addresses."
echo ""
echo "  2. Edit config.yaml — review language, model, schedule, and other settings."
echo ""
echo "  3. bash service-start.sh"
echo ""
echo "  To verify before starting the service:"
echo "     docker compose -f docker-compose.prod.yml run --rm whispercrawl --once --dry-run"
