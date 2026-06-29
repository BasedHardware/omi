#!/usr/bin/env bash
# Run the local LLM gateway as a separate FastAPI process.
#
#   cd backend && ./scripts/dev-serve-llm-gateway.sh [extra uvicorn args]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/../../scripts/dev-instance.sh"
cd "$BACKEND_DIR"

LLM_GATEWAY_PORT="${LLM_GATEWAY_PORT:-$((PYTHON_PORT + 1000))}"
PIDFILE="$OMI_DEV_DIR/llm-gateway.pid"

if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
    echo "dev-serve-llm-gateway: stopping our old gateway (pid $OLD, port $LLM_GATEWAY_PORT)"
    kill "$OLD" 2>/dev/null || true
    sleep 0.5
  fi
  rm -f "$PIDFILE"
fi

HOLDER="$(lsof -ti tcp:"$LLM_GATEWAY_PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
if [ -n "$HOLDER" ]; then
  echo "ERROR: LLM gateway port $LLM_GATEWAY_PORT (instance '$OMI_INSTANCE') is in use by pid $HOLDER:"
  echo "  $(ps -o command= -p "$HOLDER" 2>/dev/null)"
  echo "  Stop it, or run with LLM_GATEWAY_PORT=<free> / OMI_INSTANCE=<name>."
  exit 1
fi

for v in .venv venv; do
  [ -f "$v/bin/activate" ] && { source "$v/bin/activate"; break; }
done

echo "dev-serve-llm-gateway: instance='$OMI_INSTANCE' -> http://127.0.0.1:$LLM_GATEWAY_PORT"
echo $$ > "$PIDFILE"
exec python3 -m uvicorn llm_gateway.main:app --host 0.0.0.0 --port "$LLM_GATEWAY_PORT" "$@"
