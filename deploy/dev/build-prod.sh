#!/usr/bin/env bash
# build-prod.sh — build whispercrawl image, pull dependency images, and export.
# Run from the repository root:
#   bash deploy/dev/build-prod.sh
#
# Output:
#   deploy/prod/dist/whispercrawl.tar          (whispercrawl only)
#   deploy/prod-local/dist/whispercrawl.tar    \
#   deploy/prod-local/dist/whisper.tar          > all-in-one bundle
#   deploy/prod-local/dist/ollama.tar          /
#   deploy/prod/config.yaml                    (current config snapshot)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PROD_DIST="$REPO_ROOT/deploy/prod/dist"
PROD_LOCAL_DIST="$REPO_ROOT/deploy/prod-local/dist"

mkdir -p "$PROD_DIST" "$PROD_LOCAL_DIST"

# ── 1. Build whispercrawl ─────────────────────────────────────────────────────
echo "==> Building whispercrawl:latest ..."
docker build -t whispercrawl:latest "$REPO_ROOT"

# ── 2. Pull dependency images if not already present ─────────────────────────
WHISPER_IMAGE="onerahmet/openai-whisper-asr-webservice:latest"
OLLAMA_IMAGE="ollama/ollama:latest"

for IMAGE in "$WHISPER_IMAGE" "$OLLAMA_IMAGE"; do
  if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
    echo "==> Pulling $IMAGE ..."
    docker pull "$IMAGE"
  else
    echo "==> $IMAGE already present, skipping pull."
  fi
done

# ── 3. Export images ──────────────────────────────────────────────────────────

# deploy/prod — whispercrawl only (connects to external whisper + ollama)
echo "==> Saving whispercrawl:latest → deploy/prod/dist/whispercrawl.tar ..."
docker save whispercrawl:latest -o "$PROD_DIST/whispercrawl.tar"

# deploy/prod-local — all three images (all-in-one bundle)
declare -A LOCAL_IMAGES=(
  ["whispercrawl.tar"]="whispercrawl:latest"
  ["whisper.tar"]="$WHISPER_IMAGE"
  ["ollama.tar"]="$OLLAMA_IMAGE"
)

for TAR in "${!LOCAL_IMAGES[@]}"; do
  IMAGE="${LOCAL_IMAGES[$TAR]}"
  echo "==> Saving $IMAGE → deploy/prod-local/dist/$TAR ..."
  docker save "$IMAGE" -o "$PROD_LOCAL_DIST/$TAR"
done

# ── 4. Copy config snapshot ───────────────────────────────────────────────────
echo "==> Copying config.yaml to deploy/prod/ ..."
cp "$REPO_ROOT/config.yaml" "$REPO_ROOT/deploy/prod/config.yaml"

echo ""
echo "Done."
echo ""
echo "  deploy/prod/dist/       — whispercrawl.tar only (connects to external whisper + ollama)"
echo "  deploy/prod-local/dist/ — all three images (whisper + ollama + whispercrawl)"
echo ""
echo "Transfer the appropriate deploy/ subdirectory to the target host,"
echo "then run bash setup.sh."
echo ""
ls -lh "$PROD_DIST/"
