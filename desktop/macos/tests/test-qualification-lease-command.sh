#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEASE_COMMAND="$SCRIPT_DIR/../scripts/qualification-lease-command.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-qualification-lease-command-test.XXXXXX")"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

FIXTURE_WORKTREE="$TMP_ROOT/worktree"
FIXTURE_PYTHON="$FIXTURE_WORKTREE/backend/.venv/bin/python"
WORKFLOW_SOURCE="$TMP_ROOT/workflow-source"
mkdir -p "$(dirname "$FIXTURE_PYTHON")"
mkdir -p "$WORKFLOW_SOURCE"
cat > "$FIXTURE_PYTHON" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == '-m' && "${2:-}" == 'dev_harness.cli' && "${3:-}" == 'qualification-lease' && "${5:-}" == '--lease-id' ]] || {
  echo "unexpected qualification lease command shape" >&2
  exit 65
}
expected_worktree="${QUALIFICATION_LEASE_EXPECTED_WORKTREE:-}"
actual_worktree="$(pwd -P)"
expected_worktree="$(cd "$expected_worktree" && pwd -P)"
[[ "$actual_worktree" == "$expected_worktree" ]] || {
  echo "qualification lease ran from $actual_worktree instead of $expected_worktree" >&2
  exit 66
}
if [[ -n "${QUALIFICATION_LEASE_EXPECTED_PYTHON:-}" ]]; then
  actual_python="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
  expected_python="$(cd "$(dirname "$QUALIFICATION_LEASE_EXPECTED_PYTHON")" && pwd -P)/$(basename "$QUALIFICATION_LEASE_EXPECTED_PYTHON")"
  [[ "$actual_python" == "$expected_python" ]] || {
    echo "qualification lease used $actual_python instead of $expected_python" >&2
    exit 67
  }
fi
if [[ -n "${QUALIFICATION_LEASE_EXECUTION_MARKER:-}" ]]; then
  : > "$QUALIFICATION_LEASE_EXECUTION_MARKER"
fi
case "${QUALIFICATION_LEASE_FIXTURE_MODE:-}" in
  acquire-failure)
    printf '%s\n' 'Safety check failed: Qualification lease owner PID is not running: 424242'
    exit 2
    ;;
  release-failure)
    printf '%s\n' 'Safety check failed: Qualification lease token test-release-token does not match the active lease'
    exit 2
    ;;
  preflight-failure)
    printf '%s\n' 'Safety check failed: Qualification fault listener test-preflight-token lineage is unproven'
    exit 2
    ;;
  preflight-success)
    ;;
  acquire-success)
    printf '%s\n' '{"log_dir":"/tmp/qualification-log","token":"test-token"}'
    ;;
  acquire-success-with-stderr)
    printf '%s\n' 'benign harness warning' >&2
    printf '%s\n' '{"log_dir":"/tmp/qualification-log","token":"test-token"}'
    ;;
  *)
    echo "unexpected fixture mode: ${QUALIFICATION_LEASE_FIXTURE_MODE:-unset}" >&2
    exit 64
    ;;
esac
SH
chmod +x "$FIXTURE_PYTHON"

EXPLICIT_PYTHON="$TMP_ROOT/explicit/bin/python"
mkdir -p "$(dirname "$EXPLICIT_PYTHON")"
cp "$FIXTURE_PYTHON" "$EXPLICIT_PYTHON"
chmod +x "$EXPLICIT_PYTHON"
QUALIFICATION_LEASE_EXPECTED_WORKTREE="$FIXTURE_WORKTREE" \
  QUALIFICATION_LEASE_EXPECTED_PYTHON="$EXPLICIT_PYTHON" \
  QUALIFICATION_LEASE_FIXTURE_MODE=acquire-success \
  OMI_QUALIFICATION_PYTHON="$EXPLICIT_PYTHON" \
  "$LEASE_COMMAND" acquire "$FIXTURE_WORKTREE" qualification-test $$ 1000 3 >"$TMP_ROOT/explicit.out"
grep -Fxq '{"log_dir":"/tmp/qualification-log","token":"test-token"}' "$TMP_ROOT/explicit.out" \
  || fail "explicit qualification interpreter did not preserve the lease capability"

INVALID_PYTHON="$TMP_ROOT/invalid-python"
EXECUTION_MARKER="$TMP_ROOT/invalid-override-executed"
printf '%s\n' '#!/usr/bin/env bash' 'exit 99' > "$INVALID_PYTHON"
if QUALIFICATION_LEASE_EXPECTED_WORKTREE="$FIXTURE_WORKTREE" \
  QUALIFICATION_LEASE_EXECUTION_MARKER="$EXECUTION_MARKER" \
  QUALIFICATION_LEASE_FIXTURE_MODE=acquire-success \
  OMI_QUALIFICATION_PYTHON="$INVALID_PYTHON" \
  "$LEASE_COMMAND" acquire "$FIXTURE_WORKTREE" qualification-test $$ 1000 3 >"$TMP_ROOT/invalid.out" 2>"$TMP_ROOT/invalid.err"; then
  fail "invalid explicit qualification interpreter unexpectedly fell back"
fi
grep -Fq "OMI_QUALIFICATION_PYTHON is not an executable file: $INVALID_PYTHON" "$TMP_ROOT/invalid.err" \
  || fail "invalid explicit qualification interpreter was not diagnosed"
grep -Fq "attempted safe interpreter paths: OMI_QUALIFICATION_PYTHON=$INVALID_PYTHON" "$TMP_ROOT/invalid.err" \
  || fail "invalid override diagnostic omitted the attempted path"
[[ ! -e "$EXECUTION_MARKER" ]] || fail "invalid override reached lease process activity"
[[ ! -s "$TMP_ROOT/invalid.out" ]] || fail "invalid override wrote a JSON capability"

if QUALIFICATION_LEASE_EXPECTED_WORKTREE="$FIXTURE_WORKTREE" QUALIFICATION_LEASE_FIXTURE_MODE=acquire-failure "$LEASE_COMMAND" acquire "$FIXTURE_WORKTREE" qualification-test 424242 1000 3 >"$TMP_ROOT/acquire.out" 2>"$TMP_ROOT/acquire.err"; then
  fail "lease acquire unexpectedly succeeded"
fi
grep -Fq 'qualification failed: lease acquire exited 2: Safety check failed: Qualification lease owner PID is not running: 424242' "$TMP_ROOT/acquire.err" \
  || fail "lease acquire failure was not relayed to stderr"
[[ ! -s "$TMP_ROOT/acquire.out" ]] || fail "failed lease acquire wrote a JSON capability to stdout"

if QUALIFICATION_LEASE_EXPECTED_WORKTREE="$FIXTURE_WORKTREE" QUALIFICATION_LEASE_FIXTURE_MODE=release-failure "$LEASE_COMMAND" release "$FIXTURE_WORKTREE" qualification-test test-release-token 3 1209600 >"$TMP_ROOT/release.out" 2>"$TMP_ROOT/release.err"; then
  fail "lease release unexpectedly succeeded"
fi
grep -Fq 'qualification failed: lease release exited 2: Safety check failed: Qualification lease token [redacted] does not match the active lease' "$TMP_ROOT/release.err" \
  || fail "lease release failure was not relayed to stderr"
if grep -Fq 'test-release-token' "$TMP_ROOT/release.err"; then
  fail "lease release diagnostic leaked its capability token"
fi

if QUALIFICATION_LEASE_EXPECTED_WORKTREE="$FIXTURE_WORKTREE" QUALIFICATION_LEASE_FIXTURE_MODE=preflight-failure "$LEASE_COMMAND" preflight-fault-cleanup "$FIXTURE_WORKTREE" qualification-test test-preflight-token "$TMP_ROOT/preflight.json" >"$TMP_ROOT/preflight.out" 2>"$TMP_ROOT/preflight.err"; then
  fail "fault-listener preflight unexpectedly succeeded"
fi
grep -Fq 'qualification failed: lease preflight-fault-cleanup exited 2: Safety check failed: Qualification fault listener [redacted] lineage is unproven' "$TMP_ROOT/preflight.err" \
  || fail "fault-listener preflight failure was not relayed precisely"
if grep -Fq 'test-preflight-token' "$TMP_ROOT/preflight.err"; then
  fail "fault-listener preflight diagnostic leaked its capability token"
fi
QUALIFICATION_LEASE_EXPECTED_WORKTREE="$FIXTURE_WORKTREE" QUALIFICATION_LEASE_FIXTURE_MODE=preflight-success "$LEASE_COMMAND" preflight-fault-cleanup "$FIXTURE_WORKTREE" qualification-test test-preflight-token "$TMP_ROOT/preflight.json"

QUALIFICATION_LEASE_EXPECTED_WORKTREE="$FIXTURE_WORKTREE" QUALIFICATION_LEASE_FIXTURE_MODE=acquire-success "$LEASE_COMMAND" acquire "$FIXTURE_WORKTREE" qualification-test $$ 1000 3 >"$TMP_ROOT/success.out"
grep -Fxq '{"log_dir":"/tmp/qualification-log","token":"test-token"}' "$TMP_ROOT/success.out" \
  || fail "successful lease acquire did not preserve its JSON capability"

(
  cd "$WORKFLOW_SOURCE"
  QUALIFICATION_LEASE_EXPECTED_WORKTREE="$FIXTURE_WORKTREE" QUALIFICATION_LEASE_FIXTURE_MODE=acquire-success-with-stderr "$LEASE_COMMAND" acquire "$FIXTURE_WORKTREE" qualification-test $$ 1000 3
) >"$TMP_ROOT/success-with-stderr.out" 2>"$TMP_ROOT/success-with-stderr.err"
grep -Fxq '{"log_dir":"/tmp/qualification-log","token":"test-token"}' "$TMP_ROOT/success-with-stderr.out" \
  || fail "successful lease acquire with stderr did not preserve its JSON capability"
[[ ! -s "$TMP_ROOT/success-with-stderr.err" ]] \
  || fail "successful lease acquire relayed diagnostics instead of isolating its JSON capability"

SHARED_HOME="$TMP_ROOT/shared-home"
SHARED_PYTHON="$SHARED_HOME/workspace/omi/backend/.venv/bin/python"
mkdir -p "$(dirname "$SHARED_PYTHON")"
cp "$FIXTURE_PYTHON" "$SHARED_PYTHON"
chmod +x "$SHARED_PYTHON"
rm "$FIXTURE_PYTHON"
env -u OMI_QUALIFICATION_PYTHON \
  HOME="$SHARED_HOME" \
  QUALIFICATION_LEASE_EXPECTED_WORKTREE="$FIXTURE_WORKTREE" \
  QUALIFICATION_LEASE_EXPECTED_PYTHON="$SHARED_PYTHON" \
  QUALIFICATION_LEASE_FIXTURE_MODE=acquire-success \
  "$LEASE_COMMAND" acquire "$FIXTURE_WORKTREE" qualification-test $$ 1000 3 >"$TMP_ROOT/shared.out"
grep -Fxq '{"log_dir":"/tmp/qualification-log","token":"test-token"}' "$TMP_ROOT/shared.out" \
  || fail "source-only worktree did not use the canonical shared interpreter"

MISSING_HOME="$TMP_ROOT/missing-home"
mkdir -p "$MISSING_HOME"
if env -u OMI_QUALIFICATION_PYTHON \
  HOME="$MISSING_HOME" \
  "$LEASE_COMMAND" acquire "$FIXTURE_WORKTREE" qualification-test $$ 1000 3 >"$TMP_ROOT/missing.out" 2>"$TMP_ROOT/missing.err"; then
  fail "missing qualification interpreters unexpectedly succeeded"
fi
grep -Fq "worktree=$FIXTURE_WORKTREE/backend/.venv/bin/python" "$TMP_ROOT/missing.err" \
  || fail "missing interpreter diagnostic omitted the worktree path"
grep -Fq "shared=$MISSING_HOME/workspace/omi/backend/.venv/bin/python" "$TMP_ROOT/missing.err" \
  || fail "missing interpreter diagnostic omitted the shared path"
[[ ! -s "$TMP_ROOT/missing.out" ]] || fail "missing interpreters wrote a JSON capability"

echo "qualification lease command behavioral regression tests passed"
