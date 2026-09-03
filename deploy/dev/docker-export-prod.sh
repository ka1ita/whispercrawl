#!/usr/bin/env bash
# docker-export-prod.sh — build asr-crawler image, pull dependency images, and export.
# Run from the repository root:
#   bash deploy/dev/docker-export-prod.sh
#
# Output:
#   deploy/prod/dist/asr-crawler.tar          (asr-crawler only)
#   deploy/prod-local/dist/asr-crawler.tar     \
#   deploy/prod-local/dist/asr-webservice.tar    > all-in-one bundle
#   deploy/prod-local/dist/ollama.tar           /
#   deploy/prod/config.yaml                    (current config snapshot)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PROD_DIST="$REPO_ROOT/deploy/prod/dist"
PROD_LOCAL_DIST="$REPO_ROOT/deploy/prod-local/dist"

mkdir -p "$PROD_DIST" "$PROD_LOCAL_DIST"

# ── 1. Build asr-crawler ─────────────────────────────────────────────────────
echo "==> Building asr-crawler:latest ..."
docker build -t asr-crawler:latest "$REPO_ROOT"

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

# deploy/prod — asr-crawler only (connects to external asr-webservice + ollama)
echo "==> Saving asr-crawler:latest → deploy/prod/dist/asr-crawler.tar ..."
docker save asr-crawler:latest -o "$PROD_DIST/asr-crawler.tar"

# deploy/prod-local — all three images (all-in-one bundle)
declare -A LOCAL_IMAGES=(
  ["asr-crawler.tar"]="asr-crawler:latest"
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
echo "  deploy/prod/dist/       — asr-crawler.tar only (connects to external asr-webservice + ollama)"
echo "  deploy/prod-local/dist/ — all three images (asr-webservice + ollama + asr-crawler)"
echo ""
echo "Transfer the appropriate deploy/ subdirectory to the target host,"
echo "then run bash setup.sh."
echo ""
ls -lh "$PROD_DIST/"
