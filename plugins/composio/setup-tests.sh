#!/usr/bin/env bash
# Provision dependencies separately from the offline check runner.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
uv venv --allow-existing --python 3.11 .test-venv
python_bin=".test-venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin=".test-venv/Scripts/python.exe"
fi
uv pip install --python "$python_bin" -r requirements.txt
