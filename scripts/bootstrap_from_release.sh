#!/usr/bin/env bash
# One-click bootstrap: downloads GPT_SoVITS_part*.zip, assets_release.zip, and (if present on the release)
# optional fvr_deploy_output.zip into ./output.
# Set FVR_SKIP_OUTPUT=1 to skip the output bundle. Optional 5th arg: output zip name, or "skip".
#
# Asset hosts (default: GitHub Release only):
#   FVR_ASSET_BASE_URLS       Semicolon-separated base URLs (no trailing slash). If set, ONLY these are used.
#   FVR_ASSET_EXTRA_BASE_URLS When FVR_ASSET_BASE_URLS is unset, try GitHub first, then each extra base.
#   HF_TOKEN                  Optional Bearer token for private Hugging Face files.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <repo> <tag> [target_root] [assets_asset_name] [output_zip_or_skip]"
  echo "Example: $0 yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 ."
  echo "  FVR_SKIP_OUTPUT=1 $0 ...   # skip downloading ./output bundle"
  echo "  $0 ... . assets_release.zip skip   # same as FVR_SKIP_OUTPUT=1"
  echo "  FVR_ASSET_BASE_URLS='https://huggingface.co/datasets/ORG/REPO/resolve/main' $0 owner/repo tag .   # HF-only (repo/tag ignored for URLs)"
  exit 1
fi

REPO="$1"
TAG="$2"
TARGET_ROOT="${3:-.}"
ASSETS_ASSET_NAME="${4:-assets_release.zip}"
OUTPUT_ARG="${5:-fvr_deploy_output.zip}"

ROOT="$(cd "$TARGET_ROOT" && pwd)"
TMP_DIR="$ROOT/.release_tmp"
GITHUB_BASE="https://github.com/${REPO}/releases/download/${TAG}"

BASES=()
if [[ -n "${FVR_ASSET_BASE_URLS:-}" ]]; then
  IFS=';' read -r -a _parts <<< "${FVR_ASSET_BASE_URLS}"
  for x in "${_parts[@]}"; do
    x="${x#"${x%%[![:space:]]*}"}"
    x="${x%"${x##*[![:space:]]}"}"
    x="${x%/}"
    [[ -n "$x" ]] && BASES+=("$x")
  done
  if [[ "${#BASES[@]}" -eq 0 ]]; then
    echo "ERROR: FVR_ASSET_BASE_URLS is set but no non-empty base URL after parsing." >&2
    exit 1
  fi
  echo "Using FVR_ASSET_BASE_URLS (${#BASES[@]} base(s)) for downloads."
else
  BASES+=("${GITHUB_BASE}")
  if [[ -n "${FVR_ASSET_EXTRA_BASE_URLS:-}" ]]; then
    IFS=';' read -r -a _extras <<< "${FVR_ASSET_EXTRA_BASE_URLS}"
    for x in "${_extras[@]}"; do
      x="${x#"${x%%[![:space:]]*}"}"
      x="${x%"${x##*[![:space:]]}"}"
      x="${x%/}"
      [[ -n "$x" ]] && BASES+=("$x")
    done
    echo "Using GitHub + ${#_extras[@]} fallback base(s) from FVR_ASSET_EXTRA_BASE_URLS."
  else
    echo "Using GitHub Release: ${GITHUB_BASE}"
  fi
fi

download_from_bases() {
  local name="$1"
  local out="$2"
  local optional="${3:-0}"
  local ok=0
  local base url
  for base in "${BASES[@]}"; do
    url="${base}/${name}"
    echo "Trying: ${url}"
    set +e
    if [[ -n "${HF_TOKEN:-}" ]]; then
      curl -fL -H "Authorization: Bearer ${HF_TOKEN}" "${url}" -o "${out}"
    else
      curl -fL "${url}" -o "${out}"
    fi
    ec=$?
    set -e
    if [[ "$ec" -eq 0 ]] && [[ -f "${out}" ]] && [[ -s "${out}" ]]; then
      ok=1
      break
    fi
    echo "WARN: ${name} failed from ${base} (curl exit ${ec})."
    rm -f "${out}"
  done
  if [[ "$ok" -ne 1 ]]; then
    if [[ "$optional" -eq 1 ]]; then
      return 1
    fi
    echo "ERROR: Could not download ${name} from any base." >&2
    exit 1
  fi
  return 0
}

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
download_from_bases "${ASSETS_ASSET_NAME}" "$TMP_DIR/${ASSETS_ASSET_NAME}" 0
for part in GPT_SoVITS_part01.zip GPT_SoVITS_part02.zip GPT_SoVITS_part03.zip GPT_SoVITS_part04.zip; do
  download_from_bases "${part}" "$TMP_DIR/${part}" 0
done

OUTPUT_DOWNLOADED=0
if [[ -n "${OUTPUT_ASSET_NAME}" ]]; then
  echo "Downloading optional release asset: ${OUTPUT_ASSET_NAME}"
  if download_from_bases "${OUTPUT_ASSET_NAME}" "$TMP_DIR/${OUTPUT_ASSET_NAME}" 1; then
    OUTPUT_DOWNLOADED=1
  else
    echo "WARN: Optional ${OUTPUT_ASSET_NAME} missing or failed on all bases. Skipping ./output."
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
