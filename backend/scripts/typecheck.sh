#!/usr/bin/env bash
# Run the enforced backend pyright lane.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYRIGHT_PYTHON="${PYRIGHT_PYTHON:-}"
if [[ -z "$PYRIGHT_PYTHON" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
    PYRIGHT_PYTHON="$VIRTUAL_ENV/bin/python"
  elif [[ -x ".venv/bin/python" ]]; then
    PYRIGHT_PYTHON=".venv/bin/python"
  else
    PYRIGHT_PYTHON="python3"
  fi
fi

export PYRIGHT_PYTHON_FORCE_VERSION="${PYRIGHT_PYTHON_FORCE_VERSION:-1.1.403}"

# --warnings omitted: CI environments may have different stub availability
# than local dev (e.g. lc3, pydub). The pre-push hook enforces 0 warnings
# locally where the full venv is available.
"$PYRIGHT_PYTHON" -m pyright \
  -p pyrightconfig.json \
  --pythonpath "$PYRIGHT_PYTHON" \
  --level warning
