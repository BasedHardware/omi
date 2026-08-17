#!/usr/bin/env bash
# Project-local on-device STT bootstrap.
#
# Creates .local/stt/venv with Python 3.12 via uv (this Mac's python3 is 3.14;
# mlx requires >=3.10 and does not publish an assumed 3.14 wheel), installs
# mlx-whisper, and pre-downloads the default model into .local/stt/hf-cache.
#
# Default model: mlx-community/whisper-large-v3-turbo (~1.6 GB on disk).
# large-v3-turbo is the speed-optimized large-v3 distill. On Apple Silicon it
# meets the ~10s first-text target at 3s windows with far better accuracy than
# tiny/base, and it fits an M-series Max. Override with OMI_STT_MODEL.
# Idempotent. Never invoked by tests.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_STT_DIR="$ROOT/.local/stt"
DEFAULT_VENV="$DEFAULT_STT_DIR/venv"
DEFAULT_MODEL="mlx-community/whisper-large-v3-turbo"
PYTHON_VERSION="3.12"

VENV="${OMI_STT_VENV:-$DEFAULT_VENV}"
MODEL="${OMI_STT_MODEL:-$DEFAULT_MODEL}"
if [[ "$VENV" != /* ]]; then
  VENV="$ROOT/$VENV"
fi

fail() {
  printf 'stt-bootstrap: %s\n' "$1" >&2
  exit 1
}

if ! command -v uv >/dev/null 2>&1; then
  fail "uv is required. Install it from https://docs.astral.sh/uv/ then re-run scripts/stt-bootstrap.sh."
fi

STT_DIR="$(dirname "$VENV")"
mkdir -p "$STT_DIR" "$STT_DIR/hf-cache"
HF_HOME="$STT_DIR/hf-cache"
STAMP="$STT_DIR/bootstrap.json"
PYTHON="$VENV/bin/python"

stamp_matches() {
  [[ -f "$STAMP" ]] || return 1
  [[ -x "$PYTHON" ]] || return 1
  MODEL="$MODEL" STAMP="$STAMP" "$PYTHON" -c '
import json, os, sys
stamp = json.load(open(os.environ["STAMP"], encoding="utf8"))
ok = (
    stamp.get("schema") == "omi.stt-bootstrap.v1"
    and stamp.get("engine") == "mlx-whisper"
    and stamp.get("model") == os.environ["MODEL"]
)
sys.exit(0 if ok else 1)
'
}

if [[ -x "$PYTHON" ]] && "$PYTHON" -c "import mlx_whisper" >/dev/null 2>&1 && stamp_matches; then
  printf 'stt-bootstrap: already ready under .local/stt\n'
  exit 0
fi

printf 'stt-bootstrap: python %s via uv (host python is not used)\n' "$PYTHON_VERSION"
uv python install "$PYTHON_VERSION"
uv venv --python "$PYTHON_VERSION" "$VENV"

printf 'stt-bootstrap: installing mlx-whisper into the project-local venv\n'
uv pip install --python "$PYTHON" mlx-whisper

if ! "$PYTHON" -c "import mlx_whisper" >/dev/null 2>&1; then
  fail "mlx-whisper did not import after install."
fi

printf 'stt-bootstrap: downloading Whisper weights into .local/stt/hf-cache (first run is large)\n'
export HF_HOME
if ! MODEL="$MODEL" "$PYTHON" -c '
import os
from mlx_whisper.load_models import load_model
load_model(os.environ["MODEL"])
'; then
  fail "model download or load failed. Check network access to Hugging Face and retry."
fi

python_version="$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")"
MODEL="$MODEL" STAMP="$STAMP" PYTHON_VERSION="$python_version" "$PYTHON" -c '
import json, os
stamp = {
    "schema": "omi.stt-bootstrap.v1",
    "engine": "mlx-whisper",
    "model": os.environ["MODEL"],
    "python": os.environ["PYTHON_VERSION"],
}
with open(os.environ["STAMP"], "w", encoding="utf8") as handle:
    json.dump(stamp, handle)
    handle.write("\n")
'

printf 'stt-bootstrap: ready. Enable with OMI_STT_ENGINE=mlx-whisper\n'
