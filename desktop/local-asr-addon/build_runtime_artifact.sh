#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADDON_DIR="$ROOT_DIR/desktop/local-asr-addon"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/desktop/local-asr-addon/dist}"
VERSION="${LOCAL_ASR_RUNTIME_VERSION:?Set LOCAL_ASR_RUNTIME_VERSION, e.g. 2026.05.20.1}"
PYTHON_STANDALONE_DIR="${PYTHON_STANDALONE_DIR:?Set PYTHON_STANDALONE_DIR to an arm64 standalone Python runtime directory}"
SIGN_IDENTITY="${LOCAL_ASR_SIGN_IDENTITY:-${OMI_SIGN_IDENTITY:-}}"
NOTARY_PROFILE="${LOCAL_ASR_NOTARY_PROFILE:-}"

ARTIFACT_ROOT="$OUT_DIR/runtime-macos-arm64-$VERSION"
ZIP_PATH="$OUT_DIR/runtime-macos-arm64-$VERSION.zip"

rm -rf "$ARTIFACT_ROOT" "$ZIP_PATH"
mkdir -p "$ARTIFACT_ROOT" "$OUT_DIR"

rsync -a --delete "$PYTHON_STANDALONE_DIR"/ "$ARTIFACT_ROOT"/
"$ARTIFACT_ROOT/bin/python3" -m pip install \
  --no-cache-dir \
  --requirement "$ADDON_DIR/requirements.lock"

"$ARTIFACT_ROOT/bin/python3" - <<'PY'
import importlib.util
import platform
import sys

if platform.machine() != "arm64":
    raise SystemExit(f"runtime must be arm64, got {platform.machine()}")
missing = [name for name in ("mlx", "mlx_whisper", "huggingface_hub") if not importlib.util.find_spec(name)]
if missing:
    raise SystemExit(f"missing required modules: {missing}")
print(sys.executable)
PY

find "$ARTIFACT_ROOT" -type f \( -perm -111 -o -name '*.dylib' -o -name '*.so' \) -print0 |
  while IFS= read -r -d '' file; do
    if [ -n "$SIGN_IDENTITY" ]; then
      codesign --force --options runtime --sign "$SIGN_IDENTITY" "$file"
    fi
  done

if [ -n "$SIGN_IDENTITY" ]; then
  codesign --force --options runtime --sign "$SIGN_IDENTITY" "$ARTIFACT_ROOT/bin/python3"
fi

(cd "$OUT_DIR" && /usr/bin/zip -qry "$(basename "$ZIP_PATH")" "$(basename "$ARTIFACT_ROOT")")

SHA256="$(shasum -a 256 "$ZIP_PATH" | awk '{print $1}')"
SIZE_BYTES="$(stat -f%z "$ZIP_PATH")"

if [ -n "$NOTARY_PROFILE" ]; then
  xcrun notarytool submit "$ZIP_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$ZIP_PATH" || true
fi

cat <<EOF
LOCAL_ASR_RUNTIME_VERSION=$VERSION
LOCAL_ASR_RUNTIME_URL=UPLOAD_TO_GCS/runtime-macos-arm64-$VERSION.zip
LOCAL_ASR_RUNTIME_SHA256=$SHA256
LOCAL_ASR_RUNTIME_SIZE_BYTES=$SIZE_BYTES
EOF
