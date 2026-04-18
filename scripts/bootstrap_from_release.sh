#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <repo> <tag> [target_root] [assets_asset_name]"
  echo "Example: $0 yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 ."
  exit 1
fi

REPO="$1"
TAG="$2"
TARGET_ROOT="${3:-.}"
ASSETS_ASSET_NAME="${4:-assets_release.zip}"

ROOT="$(cd "$TARGET_ROOT" && pwd)"
TMP_DIR="$ROOT/.release_tmp"
BASE_URL="https://github.com/${REPO}/releases/download/${TAG}"

mkdir -p "$TMP_DIR"

echo "Downloading release assets..."
curl -fL "$BASE_URL/$ASSETS_ASSET_NAME" -o "$TMP_DIR/$ASSETS_ASSET_NAME"
for part in GPT_SoVITS_part01.zip GPT_SoVITS_part02.zip GPT_SoVITS_part03.zip GPT_SoVITS_part04.zip; do
  curl -fL "$BASE_URL/$part" -o "$TMP_DIR/$part"
done

echo "Extracting GPT_SoVITS..."
rm -rf "$ROOT/GPT_SoVITS"
mkdir -p "$ROOT/GPT_SoVITS"
for part in GPT_SoVITS_part01.zip GPT_SoVITS_part02.zip GPT_SoVITS_part03.zip GPT_SoVITS_part04.zip; do
  unzip -q "$TMP_DIR/$part" -d "$ROOT/GPT_SoVITS"
done

echo "Extracting assets..."
rm -rf "$ROOT/assets"
mkdir -p "$ROOT/assets"
unzip -q "$TMP_DIR/$ASSETS_ASSET_NAME" -d "$ROOT/assets"

rm -rf "$TMP_DIR"

echo "Bootstrap completed."
echo "Run service:"
echo "  bash ./start_wx_api.sh"
