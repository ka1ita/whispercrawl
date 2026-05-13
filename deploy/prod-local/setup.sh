#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Creating runtime directories ..."
mkdir -p audio logs

echo "==> Loading Docker images from dist/ ..."

for TAR in whispercrawl.tar whisper.tar ollama.tar; do
  if [[ ! -f "dist/$TAR" ]]; then
    echo "ERROR: dist/$TAR not found." >&2
    echo "       Run build-prod.sh on the build host and transfer the full deploy/prod-local/ directory." >&2
    exit 1
  fi
  echo "    Loading $TAR ..."
  docker load -i "dist/$TAR"
done

if [[ ! -f .env ]]; then
  echo "==> Copying .env.example → .env ..."
  cp .env.example .env
fi

echo ""
echo "Setup complete. Next steps:"
echo ""
echo "  1. Edit .env — set HF_TOKEN (required for diarization) and ASR_MODEL."
echo ""
echo "  2. Edit config.yaml — review language, model, schedule, and other settings."
echo ""
echo "  3. Pull the ollama model (first run only, requires internet or pre-seeded volume):"
echo "     docker compose -f docker-compose.prod-local.yml run --rm ollama ollama pull gemma3:1b"
echo ""
echo "  4. bash service-start.sh"
echo ""
echo "  To verify before starting the service:"
echo "     docker compose -f docker-compose.prod-local.yml run --rm whispercrawl --once --dry-run"
