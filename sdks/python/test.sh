#!/usr/bin/env bash
# Manifest-owned, network-free SDK tests against the minimum WebSocket API.
# uv only provisions test dependencies; no Bluetooth/audio/provider setup is needed.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "Python SDK tests require uv (the repository's Python environment manager)." >&2
  exit 1
fi

minimum_websockets="$(sed -n 's/^websockets>=\([0-9][0-9.]*\)$/\1/p' requirements.txt)"
if [[ ! "$minimum_websockets" =~ ^[0-9]+(\.[0-9]+)*$ ]]; then
  echo "Expected one websockets>=VERSION requirement to select the minimum-version test environment." >&2
  exit 1
fi

exec uv run --no-project --python 3.11 \
  --with 'pytest==8.4.1' \
  --with "websockets==$minimum_websockets" \
  python -m pytest tests -q
