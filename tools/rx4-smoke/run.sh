#!/usr/bin/env bash
# Bounded rx4 smoke: drive the packages/contracts ratified verify slice with an
# rx4 agent and confirm the checkout was not modified. Local opt-in tooling —
# requires cargo (rx4 MSRV 1.88), Bun, and an OpenAI-compatible endpoint.
#
#   RX4_SMOKE_UPSTREAM   full chat/completions URL of a non-streaming
#                        OpenAI-compatible endpoint (enables the SSE shim)
#   RX4_SMOKE_API_KEY    bearer key for that endpoint
#   RX4_SMOKE_MODEL      model id (default glm-5.3-flash)
#   RX4_SMOKE_PROMPT     override the task (default: the contracts slice)
set -euo pipefail
cd "$(dirname "$0")/../.."

SLICE_PROMPT='From this repository root, run exactly this bounded verification slice: bun run --cwd packages/contracts/ratified verify . Then report: (1) the exit code, (2) one sentence on what the ratified contracts suite verifies, (3) overall pass/fail. Do not modify, create, or delete any files.'
PROMPT="${RX4_SMOKE_PROMPT:-$SLICE_PROMPT}"
MODEL="${RX4_SMOKE_MODEL:-glm-5.3-flash}"
BASE="http://127.0.0.1:${SHIM_PORT:-8787}/v1"

command -v cargo >/dev/null || { echo "cargo not found (install rustup, MSRV 1.88)"; exit 1; }
[ -n "${RX4_SMOKE_API_KEY:-}" ] || { echo "set RX4_SMOKE_API_KEY"; exit 1; }
[ -x tools/rx4-smoke/target/release/rx4-smoke ] || cargo build --release --manifest-path tools/rx4-smoke/Cargo.toml

SHIM_PID=""
if [ -n "${RX4_SMOKE_UPSTREAM:-}" ]; then
  UPSTREAM_URL="$RX4_SMOKE_UPSTREAM" bun tools/rx4-smoke/sse-shim.ts &
  SHIM_PID=$!
  trap '[ -n "$SHIM_PID" ] && kill "$SHIM_PID" 2>/dev/null || true' EXIT
  sleep 1
fi

RX4_SMOKE_BASE_URL="$BASE" \
RX4_SMOKE_API_KEY="$RX4_SMOKE_API_KEY" \
RX4_SMOKE_MODEL="$MODEL" \
tools/rx4-smoke/target/release/rx4-smoke "$PROMPT"

echo
echo "== checkout cleanliness =="
if [ -z "$(git status --short)" ]; then
  echo "clean: the agent modified nothing"
else
  echo "WARNING: the agent left changes:" >&2
  git status --short >&2
  exit 1
fi
