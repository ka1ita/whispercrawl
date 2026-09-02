#!/usr/bin/env bash
# docker-export-prod.sh — build whispercrawl image, pull dependency images, and export.
# Run from the repository root:
#   bash deploy/dev/docker-export-prod.sh
#
# Output:
#   deploy/prod/dist/whispercrawl.tar          (whispercrawl only)
#   deploy/prod-local/dist/whispercrawl.tar     \
#   deploy/prod-local/dist/asr-webservice.tar    > all-in-one bundle
#   deploy/prod-local/dist/ollama.tar           /
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
# ASR_SRC_IMAGE is what the (internet-connected) build host pulls; the project
# refers to the ASR service by the vendor-neutral ASR_IMAGE everywhere else, so
# retag before saving/loading. A site that already mirrors the upstream image can
# override ASR_SRC_IMAGE.
ASR_SRC_IMAGE="${ASR_SRC_IMAGE:-onerahmet/openai-whisper-asr-webservice:latest}"
ASR_IMAGE="${ASR_IMAGE:-asr-webservice:latest}"
OLLAMA_IMAGE="ollama/ollama:latest"

for IMAGE in "$ASR_SRC_IMAGE" "$OLLAMA_IMAGE"; do
  if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
    echo "==> Pulling $IMAGE ..."
    docker pull "$IMAGE"
  else
    echo "==> $IMAGE already present, skipping pull."
  fi
done

echo "==> Tagging $ASR_SRC_IMAGE → $ASR_IMAGE ..."
docker tag "$ASR_SRC_IMAGE" "$ASR_IMAGE"

# ── 3. Export images ──────────────────────────────────────────────────────────

# deploy/prod — whispercrawl only (connects to external asr-webservice + ollama)
echo "==> Saving whispercrawl:latest → deploy/prod/dist/whispercrawl.tar ..."
docker save whispercrawl:latest -o "$PROD_DIST/whispercrawl.tar"

# deploy/prod-local — all three images (all-in-one bundle)
declare -A LOCAL_IMAGES=(
  ["whispercrawl.tar"]="whispercrawl:latest"
  ["asr-webservice.tar"]="$ASR_IMAGE"
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
echo "  deploy/prod/dist/       — whispercrawl.tar only (connects to external asr-webservice + ollama)"
echo "  deploy/prod-local/dist/ — all three images (asr-webservice + ollama + whispercrawl)"
echo ""
echo "Transfer the appropriate deploy/ subdirectory to the target host,"
echo "then run bash setup.sh."
echo ""
ls -lh "$PROD_DIST/"
