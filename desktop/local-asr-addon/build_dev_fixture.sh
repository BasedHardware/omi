#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${OMI_LOCAL_ASR_FIXTURE_DIR:-/tmp/omi-local-asr-fixture}"
PYTHON_BIN="${OMI_LOCAL_ASR_PYTHON:-python3}"
MODEL="${OMI_LOCAL_ASR_FIXTURE_MODEL:-small}"
VERSION="${OMI_LOCAL_ASR_FIXTURE_VERSION:-dev-$(date +%Y%m%d%H%M%S)}"

case "$MODEL" in
  tiny|base|small|medium|large_v3_turbo) ;;
  *) echo "Unsupported OMI_LOCAL_ASR_FIXTURE_MODEL: $MODEL" >&2; exit 2 ;;
esac

repo_for_model() {
  case "$1" in
    tiny) echo "mlx-community/whisper-tiny-mlx" ;;
    base) echo "mlx-community/whisper-base-mlx" ;;
    small) echo "mlx-community/whisper-small-mlx" ;;
    medium) echo "mlx-community/whisper-medium-mlx" ;;
    large_v3_turbo) echo "mlx-community/whisper-large-v3-turbo" ;;
  esac
}

mkdir -p "$OUT_DIR"
rm -rf "$OUT_DIR/runtime" "$OUT_DIR/model-$MODEL" "$OUT_DIR"/*.zip "$OUT_DIR/manifest.json"

PYTHON_ABS="$("$PYTHON_BIN" - <<'PY'
import os
import sys

print(os.path.realpath(sys.executable))
PY
)"

"$PYTHON_ABS" - <<'PY'
import importlib.util
import platform
import sys

missing = [name for name in ("mlx", "mlx_whisper", "huggingface_hub") if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit(
        "Python is missing required Local Whisper packages: "
        + ", ".join(missing)
        + "\nInstall them in the selected Python, or set OMI_LOCAL_ASR_PYTHON to a ready environment."
    )
if platform.machine() != "arm64":
    raise SystemExit(f"MLX Whisper fixture requires arm64 Python, got {platform.machine()}")
PY

RUNTIME_DIR="$OUT_DIR/runtime/runtime"
mkdir -p "$RUNTIME_DIR/bin"
cat > "$RUNTIME_DIR/bin/python3" <<EOF
#!/usr/bin/env bash
exec "$PYTHON_ABS" "\$@"
EOF
chmod +x "$RUNTIME_DIR/bin/python3"

RUNTIME_ZIP="$OUT_DIR/runtime-macos-arm64-$VERSION.zip"
(cd "$OUT_DIR/runtime" && /usr/bin/zip -qry "$RUNTIME_ZIP" runtime)

MODEL_REPO="$(repo_for_model "$MODEL")"
MODEL_SOURCE="${OMI_LOCAL_ASR_MODEL_DIR:-}"
if [ -z "$MODEL_SOURCE" ]; then
  MODEL_SOURCE="$("$PYTHON_ABS" - "$MODEL_REPO" <<'PY'
from huggingface_hub import snapshot_download
import sys

print(snapshot_download(repo_id=sys.argv[1], local_files_only=False))
PY
)"
fi

if [ ! -d "$MODEL_SOURCE" ]; then
  echo "Model directory does not exist: $MODEL_SOURCE" >&2
  exit 1
fi

MODEL_STAGE="$OUT_DIR/model-$MODEL/model-$MODEL"
mkdir -p "$MODEL_STAGE"
# Hugging Face snapshots are symlink trees into the cache's blobs directory.
# The artifact must be self-contained after unzip, so copy dereferenced files.
rsync -aL --delete "$MODEL_SOURCE"/ "$MODEL_STAGE"/

SAFE_MODEL="${MODEL//_/-}"
MODEL_ZIP="$OUT_DIR/model-$SAFE_MODEL-$VERSION.zip"
(cd "$OUT_DIR/model-$MODEL" && /usr/bin/zip -qry "$MODEL_ZIP" "model-$MODEL")

RUNTIME_SHA="$(shasum -a 256 "$RUNTIME_ZIP" | awk '{print $1}')"
RUNTIME_SIZE="$(stat -f%z "$RUNTIME_ZIP")"
MODEL_SHA="$(shasum -a 256 "$MODEL_ZIP" | awk '{print $1}')"
MODEL_SIZE="$(stat -f%z "$MODEL_ZIP")"

"$PYTHON_ABS" - "$OUT_DIR/manifest.json" "$RUNTIME_ZIP" "$MODEL_ZIP" "$VERSION" "$RUNTIME_SHA" "$RUNTIME_SIZE" "$MODEL" "$MODEL_SHA" "$MODEL_SIZE" <<'PY'
import json
import pathlib
import sys

manifest_path, runtime_zip, model_zip, version, runtime_sha, runtime_size, model, model_sha, model_size = sys.argv[1:]
manifest = {
    "version": 1,
    "runtime": {
        "version": version,
        "platform": "macos",
        "arch": "arm64",
        "url": pathlib.Path(runtime_zip).resolve().as_uri(),
        "sha256": runtime_sha,
        "size_bytes": int(runtime_size),
        "minimum_app_version": None,
    },
    "models": [
        {
            "model": model,
            "version": version,
            "url": pathlib.Path(model_zip).resolve().as_uri(),
            "sha256": model_sha,
            "size_bytes": int(model_size),
        }
    ],
}
pathlib.Path(manifest_path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
PY

cat <<EOF
Local ASR fixture manifest:
  file://$OUT_DIR/manifest.json

Next:
  make serve-local

serve-local auto-injects this manifest when OMI_LOCAL_ASR_MANIFEST_URL is unset.
EOF
