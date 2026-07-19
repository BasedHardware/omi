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
  local bridge_port fault_port capture output
  bridge_port="47791"
  fault_port="19081"
  capture="$fixture/fault-run.env"
  output="$fixture/fault-suite.out"

  mkdir -p "$fixture/scripts" "$fixture/e2e/flows"
  ln -s "$CORE_HARNESS" "$fixture/scripts/desktop-core-harness.sh"
  make_pkill_stub "$bin_dir"
  : >"$fixture/e2e/flows/chat-fault-5xx.yaml"

  cat >"$bin_dir/python3" <<'SH'
#!/usr/bin/env bash
exit 0
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

  cat >"$fixture/run.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

env | sort >"${OMI_FAULT_ENV_CAPTURE:?}"
while true; do
  /bin/sleep 60
done
SH
  chmod +x "$fixture/run.sh"

  cat >"$fixture/scripts/omi-harness" <<'SH'
#!/usr/bin/env python3
raise SystemExit(0)
SH
  chmod +x "$fixture/scripts/omi-harness"

  PATH="$bin_dir:$PATH" \
    OMI_FAULT_TEST_PORT="$fault_port" \
    OMI_FAULT_ENV_CAPTURE="$capture" \
    "$fixture/scripts/desktop-core-harness.sh" --fault-suite --port "$bridge_port" >"$output" 2>&1 \
    || {
      cat "$output" >&2
      fail "fault suite fixture did not complete"
    }

  python3 - "$capture" "$bridge_port" "$fault_port" <<'PY'
import sys

captured = {}
for line in open(sys.argv[1], encoding="utf-8"):
    key, value = line.rstrip("\n").split("=", 1)
    captured[key] = value

fault_url = f"http://127.0.0.1:{sys.argv[3]}"
expected = {
    "OMI_APP_NAME": "omi-fault",
    "OMI_AUTOMATION_PORT": sys.argv[2],
    "OMI_SKIP_BACKEND": "1",
    "OMI_SKIP_TUNNEL": "1",
    "OMI_PYTHON_API_URL": fault_url,
    "OMI_DESKTOP_API_URL": fault_url,
    "OMI_AUTH_API_URL": fault_url,
}
for key, value in expected.items():
    assert captured.get(key) == value, (key, captured.get(key), value)
PY
}

exercise_fault_launcher_without_backend_env() {
  local fixture="$TMP_ROOT/fault-launcher/desktop/macos"
  local bin_dir="$TMP_ROOT/fault-launcher-bin"
  local output="$TMP_ROOT/fault-launcher.out"
  local status

  mkdir -p "$fixture/Backend-Rust" "$TMP_ROOT/fault-launcher/scripts" "$bin_dir"
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
    fail "fault launcher required Backend-Rust/.env despite explicit remote fault endpoints"
  fi
  grep -Fq 'Skipping backend (OMI_SKIP_BACKEND=1)' "$output" \
    || fail "fault launcher attempted normal local Backend-Rust startup"
}

exercise_fault_suite_launch_command
exercise_fault_launcher_without_backend_env

echo "fault suite launch environment regression tests passed"
