#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -n "${INSTALL_DIR:-}" ]]; then
  : # env var already set — use as-is
elif [[ -n "${1:-}" ]]; then
  INSTALL_DIR="$1"
elif [[ -t 0 ]]; then
  read -r -p "Install directory [$SCRIPT_DIR]: " INSTALL_DIR
  INSTALL_DIR="${INSTALL_DIR:-$SCRIPT_DIR}"
else
  INSTALL_DIR="$SCRIPT_DIR"
fi

cd "$INSTALL_DIR"

echo "==> Install directory: $INSTALL_DIR"

if [[ ! -f .env ]]; then
  echo "==> Copying .env.example → .env ..."
  cp .env.example .env
fi

# shellcheck disable=SC1091
source .env
APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"

echo "==> Creating runtime directories ..."
mkdir -p audio logs db
chmod 750 audio logs db

echo "==> Loading Docker images from dist/ ..."

# whisper.tar loads as asr-webservice:latest (the compose default). If ASR_IMAGE
# in .env points at a reachable internal registry, this step is optional — the
# whisper service will pull it instead.
for TAR in whispercrawl.tar whisper.tar ollama.tar; do
  if [[ ! -f "dist/$TAR" ]]; then
    echo "ERROR: dist/$TAR not found." >&2
    echo "       Run docker-build-prod.sh on the build host and transfer the full deploy/prod-local/ directory." >&2
    exit 1
  fi
  echo "    Loading $TAR ..."
  docker load -i "dist/$TAR"
done

echo "==> Setting up docker-volume ownership (uid=$APP_UID gid=$APP_GID) ..."
if [[ "$(id -u)" -eq 0 ]]; then
  if getent group "$APP_GID" >/dev/null 2>&1; then
    GROUP_NAME="$(getent group "$APP_GID" | cut -d: -f1)"
  else
    groupadd -r -g "$APP_GID" whispercrawl
    GROUP_NAME="whispercrawl"
  fi
  if getent passwd "$APP_UID" >/dev/null 2>&1; then
    echo "    UID $APP_UID already assigned to $(getent passwd "$APP_UID" | cut -d: -f1); reusing it."
  else
    useradd -r -u "$APP_UID" -g "$GROUP_NAME" -s /usr/sbin/nologin -M whispercrawl
    echo "    Created system user 'whispercrawl' (uid=$APP_UID gid=$APP_GID)."
  fi
  chown -R "$APP_UID:$APP_GID" audio logs db
  if [[ -f config.yaml ]]; then
    chown "root:$APP_GID" config.yaml
    chmod 640 config.yaml
  fi
else
  echo "    WARNING: not running as root — skipping ownership setup." >&2
  echo "    The container runs as uid=$APP_UID gid=$APP_GID. Run this manually so it can" >&2
  echo "    read/write the mounted directories:" >&2
  echo "" >&2
  echo "      sudo groupadd -r -g $APP_GID whispercrawl 2>/dev/null || true" >&2
  echo "      sudo useradd -r -u $APP_UID -g $APP_GID -s /usr/sbin/nologin -M whispercrawl 2>/dev/null || true" >&2
  echo "      sudo chown -R $APP_UID:$APP_GID \"$INSTALL_DIR/audio\" \"$INSTALL_DIR/logs\" \"$INSTALL_DIR/db\"" >&2
  echo "      sudo chown root:$APP_GID \"$INSTALL_DIR/config.yaml\" && sudo chmod 640 \"$INSTALL_DIR/config.yaml\"" >&2
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
