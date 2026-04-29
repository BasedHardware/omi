#!/usr/bin/env bash
#
# Pi sidecar smoke test.
#
# Spawns `pi --mode rpc` with the Nooto backend extension, sends a single
# prompt over stdin (JSONL), prints all events to stdout, then exits cleanly.
#
# Required env vars before running:
#   NOOTO_BACKEND_URL   e.g. https://nooto-dev.togodynamics.com
#   NOOTO_ID_TOKEN      Firebase ID token of a user with a positive agent_code wallet
#
# Optional:
#   FOLDER              defaults to $(pwd); becomes Pi's cwd
#   PROMPT              defaults to "List the files here and summarize the project."

set -euo pipefail

: "${NOOTO_BACKEND_URL:?NOOTO_BACKEND_URL is required}"
: "${NOOTO_ID_TOKEN:?NOOTO_ID_TOKEN is required}"

FOLDER="${FOLDER:-$(pwd)}"
PROMPT="${PROMPT:-List the files here and summarize the project.}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIDECAR_DIR="$(dirname "$SCRIPT_DIR")"

cd "$SIDECAR_DIR"

cd "$FOLDER"
{
  printf '{"id":"r1","type":"prompt","message":%s}\n' "$(printf '%s' "$PROMPT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
  sleep 1
  printf '{"id":"r2","type":"shutdown"}\n'
} | "$SIDECAR_DIR/node_modules/.bin/pi" \
  --mode rpc \
  -e "$SIDECAR_DIR/extensions/nooto-backend/index.ts" \
  --provider nooto-backend \
  --model "nooto-backend/qwen3.6-35b-a3b"
