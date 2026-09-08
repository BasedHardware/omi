#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"
python_bin="${PYTHON:-$repo_root/backend/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  python_bin="python3"
fi
PYTHONPATH=backend "$python_bin" -m pytest backend/tests/unit/test_parity_pack_v0.py backend/tests/unit/test_parity_pack_v0_stage3.py "$@"
