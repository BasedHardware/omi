#!/usr/bin/env bash
# Run the plugin's regression suite without provisioning or network access.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
python_bin=".test-venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin=".test-venv/Scripts/python.exe"
fi
if [[ ! -x "$python_bin" ]]; then
  echo "Run bash plugins/composio/setup-tests.sh from the repository root first." >&2
  exit 1
fi
exec "$python_bin" -m unittest discover -s tests -v
