#!/usr/bin/env bash
# One-click bootstrap: downloads GPT_SoVITS_part*.zip, assets_release.zip, and (if present on the release)
# optional fvr_deploy_output.zip into ./output.
# Set FVR_SKIP_OUTPUT=1 to skip the output bundle. Optional 5th arg: output zip name, or "skip".
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <repo> <tag> [target_root] [assets_asset_name] [output_zip_or_skip]"
  echo "Example: $0 yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 ."
  echo "  FVR_SKIP_OUTPUT=1 $0 ...   # skip downloading ./output bundle"
  echo "  $0 ... . assets_release.zip skip   # same as FVR_SKIP_OUTPUT=1"
  exit 1
fi

REPO="$1"
TAG="$2"
TARGET_ROOT="${3:-.}"
ASSETS_ASSET_NAME="${4:-assets_release.zip}"
OUTPUT_ARG="${5:-fvr_deploy_output.zip}"

ROOT="$(cd "$TARGET_ROOT" && pwd)"
TMP_DIR="$ROOT/.release_tmp"
BASE_URL="https://github.com/${REPO}/releases/download/${TAG}"

SKIP_OUTPUT="${FVR_SKIP_OUTPUT:-0}"
if [[ "${OUTPUT_ARG}" == "skip" ]]; then
  SKIP_OUTPUT=1
fi
if [[ "${SKIP_OUTPUT}" == "1" ]]; then
  OUTPUT_ASSET_NAME=""
else
  OUTPUT_ASSET_NAME="${OUTPUT_ARG}"
fi

mkdir -p "$TMP_DIR"

echo "Downloading release assets..."
curl -fL "$BASE_URL/$ASSETS_ASSET_NAME" -o "$TMP_DIR/$ASSETS_ASSET_NAME"
for part in GPT_SoVITS_part01.zip GPT_SoVITS_part02.zip GPT_SoVITS_part03.zip GPT_SoVITS_part04.zip; do
  curl -fL "$BASE_URL/$part" -o "$TMP_DIR/$part"
done

OUTPUT_DOWNLOADED=0
if [[ -n "${OUTPUT_ASSET_NAME}" ]]; then
  echo "Downloading optional release asset: ${OUTPUT_ASSET_NAME}"
  set +e
  curl -fL "$BASE_URL/${OUTPUT_ASSET_NAME}" -o "$TMP_DIR/${OUTPUT_ASSET_NAME}"
  oc=$?
  set -e
  if [[ "$oc" -eq 0 ]] && [[ -f "$TMP_DIR/${OUTPUT_ASSET_NAME}" ]]; then
    OUTPUT_DOWNLOADED=1
  else
    echo "WARN: Optional ${OUTPUT_ASSET_NAME} not on this release or download failed. Skipping ./output."
  fi
fi

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

if [[ "$OUTPUT_DOWNLOADED" -eq 1 ]]; then
  echo "Extracting ${OUTPUT_ASSET_NAME} -> ./output"
  rm -rf "$ROOT/output"
  unzip -q "$TMP_DIR/${OUTPUT_ASSET_NAME}" -d "$ROOT"
fi

rm -rf "$TMP_DIR"

echo "Bootstrap completed."
echo "Generated:"
echo "  $ROOT/GPT_SoVITS"
echo "  $ROOT/assets"
if [[ "$OUTPUT_DOWNLOADED" -eq 1 ]]; then
  echo "  $ROOT/output"
fi
echo "Run service:"
echo "  bash ./start_wx_api.sh"
