#!/usr/bin/env bash
# shellcheck shell=bash
# Regression coverage for the fault suite's detached `open` launch contract.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CORE_HARNESS="$MACOS_DIR/scripts/desktop-core-harness.sh"
APP_CONFIG="$MACOS_DIR/scripts/app-config.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-fault-owned-app.XXXXXX")"

cleanup() {
  local pid
  for pid_file in "$TMP_ROOT"/*.pid; do
    [[ -f "$pid_file" ]] || continue
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] && kill "$pid" 2>/dev/null || true
  done
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

wait_for_file() {
  local path="$1" attempt
  for attempt in $(seq 1 100); do
    [[ -f "$path" ]] && return 0
    sleep 0.05
  done
  return 1
}

find_free_port() {
  python3 - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
}

start_port_holder() {
  local ready_file="$1"
  python3 - "$ready_file" <<'PY' &
import pathlib
import socket
import sys
import time
import os

ready_file = pathlib.Path(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    ready_tmp = ready_file.with_name(f"{ready_file.name}.tmp.{os.getpid()}")
    ready_tmp.write_text(str(sock.getsockname()[1]))
    ready_tmp.replace(ready_file)
    time.sleep(30)
PY
}

assert_dead() {
  local pid="$1" label="$2"
  if kill -0 "$pid" 2>/dev/null; then
    fail "$label (pid $pid) is still running"
  fi
}

assert_alive() {
  local pid="$1" label="$2"
  if ! kill -0 "$pid" 2>/dev/null; then
    fail "$label (pid $pid) was stopped"
  fi
}

make_fixture() {
  local fixture="$1" bin_dir="$2" flow_mode="$3"
  mkdir -p "$fixture/scripts" "$fixture/e2e/flows" "$bin_dir"
  ln -s "$CORE_HARNESS" "$fixture/scripts/desktop-core-harness.sh"
  ln -s "$APP_CONFIG" "$fixture/scripts/app-config.sh"
  : >"$fixture/e2e/flows/chat-fault-5xx.yaml"

  cat >"$bin_dir/uname" <<'SH'
#!/usr/bin/env bash
printf 'Darwin\n'
SH
  cat >"$bin_dir/git" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "-C" ]]; then printf 'deadbeef\n'; else exec /usr/bin/git "$@"; fi
SH
  cat >"$bin_dir/python3" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-" ]]; then
  program="$(cat)"
  if [[ "$program" == *"from dev_harness import config"* ]]; then
    printf '127.0.0.1:9099\n'
    exit 0
  fi
  printf '%s' "$program" | /usr/bin/python3 - "${@:2}"
  exit $?
fi
exec /usr/bin/python3 "$@"
SH
  chmod +x "$bin_dir/uname" "$bin_dir/git" "$bin_dir/python3"

  cat >"$fixture/scripts/omi-fault-inject.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  start) printf 'export OMI_FAULT_URL=%q\n' 'http://127.0.0.1:19081' ;;
  stop) : ;;
  *) exit 2 ;;
esac
SH
  cat >"$fixture/scripts/omi-ctl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == wait-ready ]]
SH
  chmod +x "$fixture/scripts/omi-fault-inject.sh" "$fixture/scripts/omi-ctl"

  cat >"$fixture/scripts/omi-harness" <<'PY'
#!/usr/bin/env python3
import os
import sys
import time
mode = os.environ["OMI_TEST_FLOW_MODE"]
if mode == "success":
    raise SystemExit(0)
if mode == "failure":
    raise SystemExit(42)
while True:
    time.sleep(1)
PY
  chmod +x "$fixture/scripts/omi-harness"

  cat >"$fixture/run.sh" <<'SH'
#!/usr/bin/env bash
# Models run.sh's `open` path: the app is detached and this launcher exits.
set -euo pipefail
: "${OMI_DESKTOP_LAUNCH_SIGNAL_FILE:?}"
: "${OMI_DESKTOP_LAUNCH_TOKEN:?}"
: "${OMI_APP_NAME:?}"
: "${OMI_AUTOMATION_PORT:?}"
: "${OMI_TEST_SERVER_ERROR_FILE:?}"
app_path="/Applications/${OMI_APP_NAME}.app"
executable_path="$app_path/Contents/MacOS/Omi Computer"
bundle_id="com.omi.${OMI_APP_NAME}"
server='import http.server,json,sys; port=int(sys.argv[1]); bundle=sys.argv[2];
class H(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  body=json.dumps({"ok":True,"bundleIdentifier":bundle}).encode(); self.send_response(200); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
 def log_message(self,*args): pass
http.server.ThreadingHTTPServer(("127.0.0.1",port),H).serve_forever()'
# The executable path is an explicit argv value in this portable model; on macOS
# the real `open ... --args` process exposes it as argv[0]. Both are checked by
# the harness alongside the unguessable token.
python3 -c "$server" "$OMI_AUTOMATION_PORT" "$bundle_id" "$executable_path" "--omi-launch-token=${OMI_DESKTOP_LAUNCH_TOKEN}" >"$OMI_TEST_SERVER_ERROR_FILE" 2>&1 &
owned_pid=$!
# If another local test owns the selected port, fail before writing launch
# ownership evidence so the caller can retry with a new port.
for _ in $(seq 1 100); do
  if [[ -s "$OMI_TEST_SERVER_ERROR_FILE" ]]; then
    wait "$owned_pid" 2>/dev/null || true
    exit 98
  fi
  if ! kill -0 "$owned_pid" 2>/dev/null; then
    wait "$owned_pid" 2>/dev/null || true
    exit 98
  fi
  sleep 0.01
done
printf '%s\n' "$owned_pid" >"${OMI_TEST_OWNED_PID_FILE:?}"
# Same executable path and bundle identity, but a different capability token.
python3 -c 'import time; time.sleep(300)' "$executable_path" "--omi-launch-token=foreign-process-token" &
foreign_pid=$!
printf '%s\n' "$foreign_pid" >"${OMI_TEST_FOREIGN_PID_FILE:?}"
umask 077
signal_tmp="${OMI_DESKTOP_LAUNCH_SIGNAL_FILE}.tmp.$$"
printf 'schema_version=1\nbundle_id=%s\napp_path=%s\nexecutable_path=%s\nlaunch_token=%s\nlaunch_transport=open\n' \
  "$bundle_id" "$app_path" "$executable_path" "$OMI_DESKTOP_LAUNCH_TOKEN" >"$signal_tmp"
mv -f "$signal_tmp" "$OMI_DESKTOP_LAUNCH_SIGNAL_FILE"
# Deliberately exit: the owned app is detached from run.sh, as with open.
SH
  chmod +x "$fixture/run.sh"
}

run_case_once() {
  local mode="$1" port="$2" attempt="$3"
  local fixture="$TMP_ROOT/$mode-$attempt" bin_dir="$TMP_ROOT/$mode-$attempt-bin"
  local owned_file="$TMP_ROOT/$mode-$attempt-owned.pid"
  local foreign_file="$TMP_ROOT/$mode-$attempt-foreign.pid"
  local output="$TMP_ROOT/$mode-$attempt.out" error_file="$fixture/server-error"
  local status=0 harness_pid=""
  local bundle="omi-fault-owned-cleanup-${mode}-${attempt}"
  local token="fault-owned-cleanup-token-${mode}-${attempt}-123456"
  make_fixture "$fixture" "$bin_dir" "$mode"

  if [[ "$mode" == term ]]; then
    PATH="$bin_dir:$PATH" OMI_TEST_FLOW_MODE="$mode" OMI_FAULT_RUN_TOKEN="$token" \
      OMI_TEST_OWNED_PID_FILE="$owned_file" OMI_TEST_FOREIGN_PID_FILE="$foreign_file" \
      OMI_TEST_SERVER_ERROR_FILE="$error_file" \
      bash "$fixture/scripts/desktop-core-harness.sh" --fault-suite --port "$port" >"$output" 2>&1 &
    harness_pid=$!
    wait_for_file "$owned_file" || { cat "$output" >&2; fail "TERM case never launched detached app"; }
    launch_records=("$fixture/.harness/desktop-core/"*-fault/fault-app.json)
    for _ in $(seq 1 100); do
      [[ -f "${launch_records[0]}" ]] && break
      sleep 0.05
      launch_records=("$fixture/.harness/desktop-core/"*-fault/fault-app.json)
    done
    [[ -f "${launch_records[0]}" ]] || { cat "$output" >&2; fail "TERM case never established launch ownership proof"; }
    kill -TERM "$harness_pid"
    set +e
    wait "$harness_pid"
    status=$?
    set -e
    [[ "$status" -eq 143 ]] || { cat "$output" >&2; fail "TERM case exited $status, expected 143"; }
  else
    set +e
    PATH="$bin_dir:$PATH" OMI_TEST_FLOW_MODE="$mode" OMI_FAULT_RUN_TOKEN="$token" \
      OMI_TEST_OWNED_PID_FILE="$owned_file" OMI_TEST_FOREIGN_PID_FILE="$foreign_file" \
      OMI_TEST_SERVER_ERROR_FILE="$error_file" \
      bash "$fixture/scripts/desktop-core-harness.sh" --fault-suite --port "$port" >"$output" 2>&1
    status=$?
    set -e
    if [[ "$mode" == success ]]; then
      if [[ "$status" -ne 0 ]]; then
        cat "$output" >&2
        return 1
      fi
    else
      if [[ "$status" -eq 0 ]]; then
        cat "$output" >&2
        fail "flow failure case unexpectedly succeeded"
      fi
    fi
  fi

  # The first attempt deliberately reserves the automation port. The launcher
  # exits before it can write ownership evidence in that case, so hand the
  # collision back to run_case() before checking the normal post-run records.
  if grep -Fq "Address already in use" "$error_file" 2>/dev/null; then
    return 1
  fi

  wait_for_file "$owned_file" || fail "$mode case did not record owned app"
  wait_for_file "$foreign_file" || fail "$mode case did not record foreign app"
  local owned_pid foreign_pid
  owned_pid="$(cat "$owned_file")"
  foreign_pid="$(cat "$foreign_file")"
  assert_dead "$owned_pid" "$mode owned detached app"
  assert_alive "$foreign_pid" "$mode foreign same-bundle app"
  kill "$foreign_pid" 2>/dev/null || true
  printf '%s\n' "$foreign_pid" >"$TMP_ROOT/foreign-cleaned.pid"

  grep -Fq '"launch_transport": "open"' "$fixture/.harness/desktop-core"/*-fault/fault-app.json \
    || fail "$mode did not retain detached open launch provenance"
  grep -Fq '"cleanup_status": "stopped"' "$fixture/.harness/desktop-core"/*-fault/fault-cleanup.json \
    || { cat "$output" >&2; fail "$mode did not write successful cleanup evidence"; }
}

run_case() {
  local mode="$1" attempt port fixture error_file
  local holder_ready="$TMP_ROOT/$mode-port-holder" holder_pid collision_retry_observed=0
  start_port_holder "$holder_ready"
  holder_pid=$!
  printf '%s\n' "$holder_pid" >"$TMP_ROOT/$mode-port-holder.pid"
  wait_for_file "$holder_ready" || fail "$mode case could not reserve a collision port"
  local held_port
  held_port="$(cat "$holder_ready")"

  for attempt in $(seq 1 5); do
    if [[ "$attempt" -eq 1 ]]; then
      port="$held_port"
    else
      port="$(find_free_port)"
    fi
    fixture="$TMP_ROOT/$mode-$attempt"
    error_file="$fixture/server-error"
    if (run_case_once "$mode" "$port" "$attempt"); then
      [[ "$collision_retry_observed" -eq 1 ]] || fail "$mode case did not exercise port-collision retry"
      return 0
    fi
    if grep -Fq "Address already in use" "$error_file" 2>/dev/null; then
      collision_retry_observed=1
      echo "Retrying $mode detached-app cleanup case after port collision (attempt $attempt)." >&2
      kill "$holder_pid" 2>/dev/null || true
      wait "$holder_pid" 2>/dev/null || true
      continue
    fi
    return 1
  done
  fail "$mode detached-app cleanup case exhausted port retries"
}

run_case success
run_case failure
run_case term

echo "fault-suite owned detached-app cleanup regressions passed"
