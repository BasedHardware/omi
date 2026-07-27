#!/usr/bin/env bash
# Build and exercise the real local Rust /health route with the release verifier.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"
BACKEND_DIR="$DESKTOP_DIR/Backend-Rust"
VERIFIER="$REPO_ROOT/.github/scripts/verify_desktop_backend_compatibility.py"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/omi-desktop-health-contract.XXXXXX")"
BACKEND_PID=""

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID"
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  rm -rf -- "$STAGE"
  exit "$rc"
}
trap cleanup EXIT INT TERM

[[ "$(uname -s)" == Darwin ]] || {
  echo "local desktop-backend compatibility verification requires macOS" >&2
  exit 1
}
[[ -x "$VERIFIER" ]] || {
  echo "desktop-backend compatibility verifier is unavailable: $VERIFIER" >&2
  exit 1
}

PORT="$(
  python3 - <<'PY'
import socket
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1])
PY
)"
BASE_URL="http://127.0.0.1:$PORT"

cargo build --manifest-path "$BACKEND_DIR/Cargo.toml"
env \
  BIND_ADDRESS=127.0.0.1 \
  FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9 \
  FIREBASE_AUTH_PROJECT_ID=omi-local-health-contract \
  FIREBASE_PROJECT_ID=omi-local-health-contract \
  GEMINI_API_KEY=not-used-by-health \
  PORT="$PORT" \
  RUST_LOG=omi_desktop_backend=warn \
  USE_VERTEX_AI=false \
  "$BACKEND_DIR/target/debug/omi-desktop-backend" >"$STAGE/backend.log" 2>&1 &
BACKEND_PID=$!

for _attempt in {1..30}; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "local Rust desktop-backend exited before /health became available" >&2
    exit 1
  fi
  if python3 - "$BASE_URL/health" <<'PY' >/dev/null 2>&1
import sys
import urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=1) as response:
    if response.status != 200:
        raise SystemExit(1)
PY
  then
    break
  fi
  sleep 1
done

LISTENER_ADDRESS="$(
  lsof -nP -a -p "$BACKEND_PID" -iTCP:"$PORT" -sTCP:LISTEN -Fn \
    | awk '/^n/ { print substr($0, 2) }'
)"
if [[ "$LISTENER_ADDRESS" != "127.0.0.1:$PORT" ]]; then
  echo "local Rust desktop-backend must listen only on 127.0.0.1:$PORT; observed ${LISTENER_ADDRESS:-no listener}" >&2
  exit 1
fi

"$VERIFIER" \
  --base-url "$BASE_URL" \
  --expected-contract-version 1 \
  --evidence "$STAGE/desktop-backend-compatibility.json"
python3 -m json.tool "$STAGE/desktop-backend-compatibility.json"
