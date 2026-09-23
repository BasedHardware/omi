#!/usr/bin/env bash
# Run the local Python backend on a PER-WORKTREE port so parallel agents/worktrees don't
# fight over 8080 (which silently clobbers each other). Derives PYTHON_PORT from the current
# worktree via scripts/dev-instance.sh, kills only its OWN previous instance, and refuses to
# steal a port another worktree owns.
#
#   cd backend && ./scripts/dev-serve.sh [extra uvicorn args]
#
# The primary checkout keeps port 8080; linked worktrees get 8080+offset.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/../../scripts/dev-instance.sh"
cd "$BACKEND_DIR"

PIDFILE="$OMI_DEV_DIR/python-backend.pid"

# Reclaim only our own previous backend (never another worktree's).
if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
    echo "dev-serve: stopping our old backend (pid $OLD, port $PYTHON_PORT)"
    kill "$OLD" 2>/dev/null || true
    sleep 0.5
  fi
  rm -f "$PIDFILE"
fi

# Fail loud if the port is held by something else — likely another worktree's backend.
HOLDER="$(lsof -ti tcp:"$PYTHON_PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
if [ -n "$HOLDER" ]; then
  echo "ERROR: Python backend port $PYTHON_PORT (instance '$OMI_INSTANCE') is in use by pid $HOLDER:"
  echo "  $(ps -o command= -p "$HOLDER" 2>/dev/null)"
  echo "  Another worktree probably owns it. Stop it, or run with PYTHON_PORT=<free> / OMI_INSTANCE=<name>."
  exit 1
fi

# Activate a local venv if one exists.
for v in .venv venv; do
  [ -f "$v/bin/activate" ] && { source "$v/bin/activate"; break; }
done

echo "dev-serve: instance='$OMI_INSTANCE' → http://127.0.0.1:$PYTHON_PORT"
echo $$ > "$PIDFILE"  # exec keeps this PID, so the pidfile points at uvicorn
exec python3 -m uvicorn main:app --host 0.0.0.0 --port "$PYTHON_PORT" "$@"
