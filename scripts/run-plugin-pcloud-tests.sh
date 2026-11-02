#!/usr/bin/env bash
# #20498's green checks never ran its FastAPI suite. Exercise the installed
# service and cross-service signing contract in both manifest lanes.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
plugin_root="$repo_root/plugins/omi-pcloud-app"
python_version="$(tr -d '[:space:]' < "$repo_root/backend/.python-version")"
cd "$plugin_root"
if ! command -v uv >/dev/null 2>&1; then
  echo 'pCloud verification requires uv to install the pinned service dependencies.' >&2
  exit 1
fi
uv run --no-project --python "$python_version" \
  --with-requirements requirements.txt --with 'pytest==8.4.1' --with 'httpx==0.28.0' \
  -- python -m pytest test_app.py test_pcloud_client.py -q
