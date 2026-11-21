#!/usr/bin/env bash
# LOCAL-STACK SMOKE for the pipeline lab (not a unit test). Synthetic data, fake LLM upstream.
# Starts a Firestore emulator and redis-server on non-default loopback ports, runs
# testing.pipeline_lab.stack.chain_smoke, and stops what it started by PID.
#   FS_PORT=8295 REDIS_PORT=6391 backend/testing/pipeline_lab/stack/run_chain_smoke.sh [--keep DIR]
# SMOKE_MODULE=testing.pipeline_lab.v3.smoke runs the conversations-v3 smoke instead.
set -euo pipefail
BACKEND="$(cd "$(dirname "$0")/../../.." && pwd)"
FS_PORT="${FS_PORT:-8295}"
REDIS_PORT="${REDIS_PORT:-6391}"
PY="${PY:-$BACKEND/.venv/bin/python}"
SMOKE_MODULE="${SMOKE_MODULE:-testing.pipeline_lab.stack.chain_smoke}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/plab-smoke-stack.XXXXXX")"
for port in "$FS_PORT" "$REDIS_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then echo "port $port is busy" >&2; exit 2; fi
done
redis-server --port "$REDIS_PORT" --bind 127.0.0.1 --save '' --appendonly no --dir "$WORK" >"$WORK/redis.log" 2>&1 &
REDIS_PID=$!
cleanup() { kill "$REDIS_PID" 2>/dev/null || true; wait "$REDIS_PID" 2>/dev/null || true; }
trap cleanup EXIT
cat >"$WORK/firebase.json" <<JSON
{"emulators": {"firestore": {"host": "127.0.0.1", "port": $FS_PORT}, "ui": {"enabled": false}, "singleProjectMode": true}}
JSON
cd "$WORK"
firebase emulators:exec --only firestore --project demo-omi-local \
  "cd '$BACKEND' && OMI_PIPELINE_LAB_REDIS=127.0.0.1:$REDIS_PORT '$PY' -m $SMOKE_MODULE $*"
