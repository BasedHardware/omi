#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:?Usage: build_model_artifact.sh <tiny|base|small|medium|large_v3_turbo> <version> <model-directory>}"
VERSION="${2:?Usage: build_model_artifact.sh <tiny|base|small|medium|large_v3_turbo> <version> <model-directory>}"
MODEL_DIR="${3:?Usage: build_model_artifact.sh <tiny|base|small|medium|large_v3_turbo> <version> <model-directory>}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/desktop/local-asr-addon/dist}"
SAFE_MODEL="${MODEL//_/-}"
STAGE="$OUT_DIR/model-$SAFE_MODEL-$VERSION"
ZIP_PATH="$OUT_DIR/model-$SAFE_MODEL-$VERSION.zip"

case "$MODEL" in
  tiny|base|small|medium|large_v3_turbo) ;;
  *) echo "Unsupported model: $MODEL" >&2; exit 2 ;;
esac

rm -rf "$STAGE" "$ZIP_PATH"
mkdir -p "$STAGE" "$OUT_DIR"
rsync -a --delete "$MODEL_DIR"/ "$STAGE"/

(cd "$OUT_DIR" && /usr/bin/zip -qry "$(basename "$ZIP_PATH")" "$(basename "$STAGE")")

SHA256="$(shasum -a 256 "$ZIP_PATH" | awk '{print $1}')"
SIZE_BYTES="$(stat -f%z "$ZIP_PATH")"
ENV_MODEL="$(echo "$MODEL" | tr '[:lower:]' '[:upper:]')"

cat <<EOF
LOCAL_ASR_MODEL_${ENV_MODEL}_VERSION=$VERSION
LOCAL_ASR_MODEL_${ENV_MODEL}_SHA256=$SHA256
LOCAL_ASR_MODEL_${ENV_MODEL}_SIZE_BYTES=$SIZE_BYTES
EOF
