#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MACOS_DIR/../.." && pwd)"
CORE_HARNESS="$MACOS_DIR/scripts/desktop-core-harness.sh"

TMP_ROOT="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

write_stub_binaries() {
  local bin_dir="$1"
  mkdir -p "$bin_dir"

  cat >"$bin_dir/uname" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "-s" ]]; then
  printf 'Darwin\n'
  exit 0
fi
exec /usr/bin/uname "$@"
SH

  cat >"$bin_dir/git" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "-C" && "${3:-}" == "rev-parse" && "${4:-}" == "HEAD" ]]; then
  printf 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n'
  exit 0
fi
exec /usr/bin/git "$@"
SH

  cat >"$bin_dir/make" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
log="${OMI_TEST_MAKE_LOG:?}"
case "$*" in
  *dev-up*)
    : >"${OMI_TEST_DEV_UP_MARKER:?}"
    printf 'dev-up\n' >>"$log"
    ;;
  *dev-down*)
    printf 'dev-down\n' >>"$log"
    ;;
esac
exit 0
SH

  cat >"$bin_dir/python3" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

scenario="${OMI_TEST_SCENARIO:?}"

if [[ "${1:-}" == "-" ]]; then
  script="$(cat)"
  if [[ "$script" == *"REQUIRED_SERVICES"* ]]; then
    if [[ "$scenario" == "ensure_dev_stack_fail" && -f "${OMI_TEST_DEV_UP_MARKER:-}" ]]; then
      printf '%s\n' '{"healthy":false,"reason":"injected_probe_failure"}'
      exit 1
    fi
    if [[ -f "${OMI_TEST_DEV_UP_MARKER:-}" || "$scenario" == "success" || "$scenario" == "keep_stack_fail" ]]; then
      printf '%s\n' '{"healthy":true,"provider_mode":"offline","config_digest_path":"/tmp/digest.json","instance":"default","state_root":"/tmp/state"}'
      exit 0
    fi
    printf '%s\n' '{"healthy":false,"reason":"stack_not_started"}'
    exit 1
  fi
  if [[ "$script" == *"manifest"* ]]; then
    exit 0
  fi
  exit 0
fi

script_path="${2:-${1:-}}"
case "$(basename "$script_path")" in
  desktop-flow-lint.py|agent-continuity-gauntlet-lib.py)
    if [[ "$scenario" == "self_check_fail" || "$scenario" == "keep_stack_fail" ]]; then
      exit 1
    fi
  ;;
esac
if [[ "$script_path" == *"/backend/testing/contracts"* ]]; then
  exit 0
fi
if [[ "$script_path" == *"-c"* ]]; then
  exit 0
fi
exit 0
SH

  chmod +x "$bin_dir/uname" "$bin_dir/git" "$bin_dir/make" "$bin_dir/python3"
}

prepare_fixture_repo() {
  local fixture="$1"
  mkdir -p "$fixture/desktop/macos/scripts" "$fixture/backend/testing/contracts"
  ln -s "$CORE_HARNESS" "$fixture/desktop/macos/scripts/desktop-core-harness.sh"
  printf '# stub\n' >"$fixture/desktop/macos/scripts/desktop-flow-lint.py"
  printf '# stub\n' >"$fixture/desktop/macos/scripts/agent-continuity-gauntlet-lib.py"
  cat >"$fixture/backend/test-preflight.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  chmod +x "$fixture/backend/test-preflight.sh"
}

run_readiness_case() {
  local scenario="$1"
  local keep_stack="${2:-0}"
  local fixture="$TMP_ROOT/$scenario"
  local bin_dir="$TMP_ROOT/${scenario}-bin"
  local make_log="$fixture/make.log"
  local dev_up_marker="$fixture/dev-up.marker"
  local output="$fixture/output.txt"
  local status=0
  local args=(--readiness)

  rm -rf "$fixture"
  prepare_fixture_repo "$fixture"
  write_stub_binaries "$bin_dir"
  : >"$make_log"
  rm -f "$dev_up_marker"

  if [[ "$keep_stack" -eq 1 ]]; then
    args+=(--keep-stack)
  fi

  set +e
  PATH="$bin_dir:$PATH" \
    OMI_TEST_SCENARIO="$scenario" \
    OMI_TEST_MAKE_LOG="$make_log" \
    OMI_TEST_DEV_UP_MARKER="$dev_up_marker" \
    bash "$fixture/desktop/macos/scripts/desktop-core-harness.sh" "${args[@]}" >"$output" 2>&1
  status=$?
  set -e

  printf '%s\n' "$status" "$make_log"
}

count_make_target() {
  local log="$1"
  local target="$2"
  grep -c "^${target}$" "$log" || true
}

assert_self_check_failure_triggers_dev_down() {
  local parsed status make_log
  parsed="$(run_readiness_case self_check_fail)"
  status="$(printf '%s\n' "$parsed" | sed -n '1p')"
  make_log="$(printf '%s\n' "$parsed" | sed -n '2p')"
  [[ "$status" -ne 0 ]] || fail "self_check failure should exit non-zero"
  [[ "$(count_make_target "$make_log" dev-down)" -eq 1 ]] || fail "self_check failure must run dev-down once (got: $(cat "$make_log"))"
  [[ "$(count_make_target "$make_log" dev-up)" -eq 0 ]] || fail "self_check failure must not start dev-up"
}

assert_ensure_dev_stack_failure_triggers_dev_down() {
  local parsed status make_log
  parsed="$(run_readiness_case ensure_dev_stack_fail)"
  status="$(printf '%s\n' "$parsed" | sed -n '1p')"
  make_log="$(printf '%s\n' "$parsed" | sed -n '2p')"
  [[ "$status" -ne 0 ]] || fail "ensure_dev_stack failure should exit non-zero"
  [[ "$(count_make_target "$make_log" dev-up)" -eq 1 ]] || fail "ensure_dev_stack failure must start dev-up before failing"
  [[ "$(count_make_target "$make_log" dev-down)" -eq 1 ]] || fail "ensure_dev_stack failure must run dev-down once (got: $(cat "$make_log"))"
}

assert_keep_stack_skips_dev_down_on_failure() {
  local parsed status make_log
  parsed="$(run_readiness_case keep_stack_fail 1)"
  status="$(printf '%s\n' "$parsed" | sed -n '1p')"
  make_log="$(printf '%s\n' "$parsed" | sed -n '2p')"
  [[ "$status" -ne 0 ]] || fail "keep-stack failure should exit non-zero"
  [[ "$(count_make_target "$make_log" dev-down)" -eq 0 ]] || fail "--keep-stack must skip dev-down on failure (got: $(cat "$make_log"))"
}

assert_success_teardowns_once() {
  local parsed status make_log
  parsed="$(run_readiness_case success)"
  status="$(printf '%s\n' "$parsed" | sed -n '1p')"
  make_log="$(printf '%s\n' "$parsed" | sed -n '2p')"
  [[ "$status" -eq 0 ]] || fail "readiness success should exit zero"
  [[ "$(count_make_target "$make_log" dev-down)" -eq 1 ]] || fail "readiness success must run dev-down exactly once (got: $(cat "$make_log"))"
}

assert_self_check_failure_triggers_dev_down
assert_ensure_dev_stack_failure_triggers_dev_down
assert_keep_stack_skips_dev_down_on_failure
assert_success_teardowns_once

echo "desktop-core-harness readiness teardown tests passed"
