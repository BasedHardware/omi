#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${FIRESTORE_EMULATOR_JAR:?Set FIRESTORE_EMULATOR_JAR to the local Firestore emulator JAR}"
pager_python=${PAGER_PYTHON:-../../.paging-venv/bin/python}
pager_java=${PAGER_JAVA:-java}
pager_port=$("$pager_python" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
pager_log=$(mktemp)
"$pager_java" -jar "$FIRESTORE_EMULATOR_JAR" --host 127.0.0.1 --port "$pager_port" \
  --project_id demo-omi-paging --single_project_mode true --single_project_mode_error true >"$pager_log" 2>&1 &
pager_pid=$!
cleanup() {
  kill "$pager_pid" 2>/dev/null || true
  wait "$pager_pid" 2>/dev/null || true
  rm -f "$pager_log"
}
trap cleanup EXIT
for ((pager_try=0; pager_try<100; pager_try++)); do
  if rg -q 'Dev App Server is now running' "$pager_log"; then
    FIRESTORE_EMULATOR_HOST="127.0.0.1:$pager_port" PYTHONPATH=.. "$pager_python" -m paging.fixture
    exit
  fi
  if ! kill -0 "$pager_pid" 2>/dev/null; then break; fi
  sleep 0.1
done
cat "$pager_log" >&2
exit 1
