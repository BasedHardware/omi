#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MACOS_DIR/../.." && pwd)"
CORE_HARNESS="$MACOS_DIR/scripts/desktop-core-harness.sh"
RUN_SH="$MACOS_DIR/run.sh"

TMP_ROOT="$(mktemp -d)"
cleanup() {
  local pid
  if [[ -f "$TMP_ROOT/fault-suite/fault-app.pid" ]]; then
    pid="$(cat "$TMP_ROOT/fault-suite/fault-app.pid" 2>/dev/null || true)"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] && kill "$pid" 2>/dev/null || true
  fi
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

make_pkill_stub() {
  local bin_dir="$1"
  mkdir -p "$bin_dir"
  cat >"$bin_dir/pkill" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  chmod +x "$bin_dir/pkill"
}

exercise_fault_suite_launch_command() {
  local fixture="$TMP_ROOT/fault-suite"
  local bin_dir="$TMP_ROOT/fault-suite-bin"
  local bridge_port fault_port fault_run_token capture ready_capture output
  local qualification_fault_state
  bridge_port="47791"
  fault_port="19081"
  fault_run_token="faultsuitefixturetoken123456"
  capture="$fixture/fault-run.env"
  ready_capture="$fixture/fault-ready.env"
  output="$fixture/fault-suite.out"
  qualification_fault_state="$fixture/qualification-state/fault"

  mkdir -p "$fixture/scripts" "$fixture/e2e/flows"
  ln -s "$CORE_HARNESS" "$fixture/scripts/desktop-core-harness.sh"
  ln -s "$MACOS_DIR/scripts/app-config.sh" "$fixture/scripts/app-config.sh"
  make_pkill_stub "$bin_dir"
  : >"$fixture/e2e/flows/chat-fault-5xx.yaml"

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
  chmod +x "$bin_dir/python3"


  cat >"$fixture/scripts/omi-fault-inject.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  start)
    printf 'export OMI_FAULT_URL=%q\n' "http://127.0.0.1:${OMI_FAULT_TEST_PORT:?}"
    ;;
  stop)
    ;;
  *)
    exit 2
    ;;
esac
SH
  chmod +x "$fixture/scripts/omi-fault-inject.sh"

  cat >"$fixture/scripts/omi-ctl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == "wait-ready" && "${2:-}" == "90" ]]
printf '%s\n' "OMI_AUTOMATION_PORT=${OMI_AUTOMATION_PORT:?}" >"${OMI_FAULT_READY_CAPTURE:?}"
SH
  chmod +x "$fixture/scripts/omi-ctl"

  cat >"$fixture/run.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

: "${OMI_FAULT_ENV_CAPTURE:?}"
: "${OMI_FAULT_APP_PID_FILE:?}"
: "${OMI_DESKTOP_LAUNCH_SIGNAL_FILE:?}"
: "${OMI_DESKTOP_LAUNCH_TOKEN:?}"
: "${OMI_APP_NAME:?}"
app_path="/Applications/${OMI_APP_NAME}.app"
executable_path="$app_path/Contents/MacOS/Omi Computer"
# Model the detached app with a real bridge process. Its final argv entries bind
# the expected executable path and run-unique launch token, so the harness uses
# the same real ps-based ownership validation as it does for an app launched by
# `open` rather than a fixture-only ps response.
bundle_id="com.omi.${OMI_APP_NAME}"
server='import http.server,json,sys; port=int(sys.argv[1]); bundle=sys.argv[2];
class H(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  body=json.dumps({"ok":True,"bundleIdentifier":bundle}).encode(); self.send_response(200); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
 def log_message(self,*args): pass
http.server.ThreadingHTTPServer(("127.0.0.1",port),H).serve_forever()'
python3 -c "$server" "$OMI_AUTOMATION_PORT" "$bundle_id" "$executable_path" "--omi-launch-token=${OMI_DESKTOP_LAUNCH_TOKEN}" &
printf '%s\n' "$!" >"$OMI_FAULT_APP_PID_FILE"
{
  printf 'schema_version=1\n'
  printf 'bundle_id=%s\n' "$bundle_id"
  printf 'app_path=%s\n' "$app_path"
  printf 'executable_path=%s\n' "$executable_path"
  printf 'launch_token=%s\n' "$OMI_DESKTOP_LAUNCH_TOKEN"
  printf 'launch_transport=open\n'
} >"$OMI_DESKTOP_LAUNCH_SIGNAL_FILE"
chmod 600 "$OMI_DESKTOP_LAUNCH_SIGNAL_FILE"
env | sort >"$OMI_FAULT_ENV_CAPTURE"
SH
  chmod +x "$fixture/run.sh"

  cat >"$fixture/scripts/omi-harness" <<'SH'
#!/usr/bin/env python3
raise SystemExit(0)
SH
  chmod +x "$fixture/scripts/omi-harness"

  PATH="$bin_dir:$PATH" \
    OMI_FAULT_RUN_TOKEN="$fault_run_token" \
    OMI_FAULT_STATE_DIR="$qualification_fault_state" \
    OMI_FAULT_APP_PID_FILE="$fixture/fault-app.pid" \
    OMI_FAULT_TEST_PORT="$fault_port" \
    OMI_FAULT_ENV_CAPTURE="$capture" \
    OMI_FAULT_READY_CAPTURE="$ready_capture" \
    "$fixture/scripts/desktop-core-harness.sh" --fault-suite --port "$bridge_port" >"$output" 2>&1 \
    || {
      cat "$output" >&2
      fail "fault suite fixture did not complete"
    }
  [[ -d "$qualification_fault_state" ]] \
    || fail "fault suite ignored the qualification-owned fault state directory"

  python3 - "$capture" "$ready_capture" "$bridge_port" "$fault_port" "$fault_run_token" "$fixture" <<'PY'
import json
from pathlib import Path
import sys

captured = {}
for line in open(sys.argv[1], encoding="utf-8"):
    key, value = line.rstrip("\n").split("=", 1)
    captured[key] = value

fault_url = f"http://127.0.0.1:{sys.argv[4]}"
fault_bundle = f"omi-fault-{sys.argv[5]}"
expected = {
    "OMI_APP_NAME": fault_bundle,
    "OMI_AUTOMATION_PORT": sys.argv[3],
    "OMI_DESKTOP_LOCAL_PROFILE": "1",
    "OMI_HARNESS_INSTANCE": "fault-suite",
    "OMI_SKIP_AUTH_SEED": "1",
    "OMI_SKIP_SETTINGS_SEED": "1",
    "OMI_LOCAL_PROFILE_STORAGE_NAME": fault_bundle,
    "OMI_LOCAL_AUTH_USER": "alice",
    "OMI_LOCAL_AUTH_EMAIL": "alice@local.omi.invalid",
    "OMI_LOCAL_AUTH_PASSWORD": "alice-local-password-030",
    "OMI_LOCAL_AUTH_DISPLAY_NAME": "Synthetic Alice",
    "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
    "FIREBASE_PROJECT_ID": "demo-omi-local",
    "FIREBASE_AUTH_PROJECT_ID": "demo-omi-local",
    "FIRESTORE_DATABASE_ID": "(default)",
    "FIREBASE_API_KEY": "local-firebase-auth-emulator-api-key",
    "OMI_ALLOW_ADHOC_SIGN": "1",
    "OMI_SKIP_BACKEND": "1",
    "OMI_SKIP_TUNNEL": "1",
    "OMI_PYTHON_API_URL": fault_url,
    "OMI_DESKTOP_API_URL": fault_url,
    "OMI_AUTH_API_URL": fault_url,
    "OMI_FAULT_MODEL_AUTH_TOKEN": "omi-fault-model-token",
    "OMI_DESKTOP_LAUNCH_TOKEN": sys.argv[5],
}
for key, value in expected.items():
    assert captured.get(key) == value, (key, captured.get(key), value)

ready = dict(line.rstrip("\n").split("=", 1) for line in open(sys.argv[2], encoding="utf-8"))
assert ready.get("OMI_AUTOMATION_PORT") == sys.argv[3], ready

records = list(Path(sys.argv[6]).glob(".harness/desktop-core/*-fault/fault-app.json"))
assert len(records) == 1, records
record = json.loads(records[0].read_text(encoding="utf-8"))
assert record["run_token"] == sys.argv[5], record
assert record["bundle"] == fault_bundle, record
assert record["bundle_id"] == f"com.omi.{fault_bundle}", record
assert record["automation_port"] == int(sys.argv[3]), record
assert record["launch_transport"] == "open", record
PY

  local app_pid
  app_pid="$(cat "$fixture/fault-app.pid")"
  if kill -0 "$app_pid" 2>/dev/null; then
    fail "fault suite cleanup left its owned detached app running"
  fi

  set +e
  PATH="$bin_dir:$PATH" \
    OMI_FAULT_RUN_TOKEN="$fault_run_token" \
    OMI_FAULT_STATE_DIR="$qualification_fault_state" \
    OMI_FAULT_APP_PID_FILE="$fixture/fault-app.pid" \
    OMI_FAULT_TEST_PORT="$fault_port" \
    OMI_FAULT_ENV_CAPTURE="$capture" \
    OMI_FAULT_READY_CAPTURE="$ready_capture" \
    OMI_FAULT_BRIDGE_READY_ATTEMPTS=not-a-number \
    "$fixture/scripts/desktop-core-harness.sh" --fault-suite --port "$bridge_port" >"$output" 2>&1
  status=$?
  set -e
  [[ "$status" -ne 0 ]] || fail "fault suite accepted a non-numeric bridge readiness attempt budget"
  grep -Fq 'OMI_FAULT_BRIDGE_READY_ATTEMPTS must be a positive integer' "$output" \
    || fail "fault suite did not report the invalid bridge readiness attempt budget"
}

exercise_fault_launcher_without_backend_env() {
  local fixture="$TMP_ROOT/fault-launcher/desktop/macos"
  local bin_dir="$TMP_ROOT/fault-launcher-bin"
  local output="$TMP_ROOT/fault-launcher.out"
  local status

  mkdir -p "$fixture" "$TMP_ROOT/fault-launcher/scripts" "$TMP_ROOT/fault-launcher/backend" "$bin_dir"
  ln -s "$RUN_SH" "$fixture/run.sh"
  ln -s "$MACOS_DIR/scripts" "$fixture/scripts"
  ln -s "$REPO_ROOT/scripts/dev-instance.sh" "$TMP_ROOT/fault-launcher/scripts/dev-instance.sh"

  cat >"$bin_dir/git" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "rev-parse" && "${2:-}" == "--show-toplevel" ]]; then
  printf '%s\n' "${OMI_FAULT_TEST_REPO_ROOT:?}"
  exit 0
fi
exec /usr/bin/git "$@"
SH
  cat >"$bin_dir/pkill" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  cat >"$bin_dir/pgrep" <<'SH'
#!/usr/bin/env bash
printf '424242\n'
SH
  cat >"$bin_dir/ps" <<'SH'
#!/usr/bin/env bash
if [[ " $* " == *" lstart= "* ]]; then
  printf 'Thu Jan  1 00:00:00 1970\n'
  exit 0
fi
if [[ " $* " == *" command= "* ]]; then
  printf 'swift-build fault-launcher\n'
  exit 0
fi
exec /bin/ps "$@"
SH
  cat >"$bin_dir/lsof" <<'SH'
#!/usr/bin/env bash
printf 'n%s\n' "${OMI_FAULT_TEST_MACOS_DIR:?}"
SH
  cat >"$bin_dir/sleep" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "2" ]]; then
  exit 97
fi
exit 0
SH
  chmod +x "$bin_dir/git" "$bin_dir/pkill" "$bin_dir/pgrep" "$bin_dir/ps" "$bin_dir/lsof" "$bin_dir/sleep"

  set +e
  PATH="$bin_dir:$PATH" \
    OMI_FAULT_TEST_REPO_ROOT="$TMP_ROOT/fault-launcher" \
    OMI_FAULT_TEST_MACOS_DIR="$fixture" \
    OMI_APP_NAME="omi-fault-launch-env-test" \
    OMI_AUTOMATION_PORT="47792" \
    OMI_SKIP_BACKEND=1 \
    OMI_SKIP_TUNNEL=1 \
    OMI_PYTHON_API_URL="http://127.0.0.1:19081" \
    OMI_DESKTOP_API_URL="http://127.0.0.1:19081" \
    OMI_AUTH_API_URL="http://127.0.0.1:19081" \
    OMI_SIGN_IDENTITY="fault-test-identity" \
    bash "$fixture/run.sh" >"$output" 2>&1
  status=$?
  set -e

  if [[ "$status" -ne 97 ]]; then
    cat "$output" >&2
    fail "fault launcher stopped before reaching the post-bootstrap sentinel (status $status)"
  fi
  if grep -Fq 'No .env file found' "$output"; then
    cat "$output" >&2
    fail "fault launcher required a backend .env despite explicit remote fault endpoints"
  fi
  grep -Fq 'Skipping backend (OMI_SKIP_BACKEND=1)' "$output" \
    || fail "fault launcher attempted normal local backend startup"
}

exercise_fault_suite_launch_command
exercise_fault_launcher_without_backend_env

echo "fault suite launch environment regression tests passed"
