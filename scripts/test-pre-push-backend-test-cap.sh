#!/usr/bin/env bash
set -euo pipefail

# The pre-push hooks export their own repository environment; an author pushing
# with a backend hatch set (e.g. PRE_PUSH_SKIP_BACKEND_UNIT_TESTS=1) must not
# leak into this lane — the cap logic has to run regardless of how the author
# is pushing.
unset PRE_PUSH_SKIP_BACKEND_UNIT_TESTS PRE_PUSH_SKIP_BACKEND_TYPECHECK PRE_PUSH_SKIP_BACKEND_RUNTIME_ENV

# Do not pass a caller's repository selection to nested fixture Git commands.
# GIT_NAMESPACE is repository-scoped but absent from Git's local-env-vars list.
GIT_LOCAL_ENV_VARS="$(git rev-parse --local-env-vars)"
for git_env_var in $GIT_LOCAL_ENV_VARS GIT_NAMESPACE; do
  unset "$git_env_var"
done
unset GIT_LOCAL_ENV_VARS git_env_var

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/scripts/pre-push"
WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

FUNC="$WORK/check_backend_unit_tests_if_needed.sh"
awk '/^check_backend_unit_tests_if_needed\(\) \{$/,/^\}$/' "$HOOK" > "$FUNC"
if ! grep -q '^}$' "$FUNC"; then
  echo "FAIL: could not extract check_backend_unit_tests_if_needed from $HOOK" >&2
  exit 1
fi

# Stub interpreter standing in for the backend selector: emits a caller-chosen
# number of selected test paths plus a reason.
cat > "$WORK/fake-python" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
output=""
reason_output=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output="$2"; shift 2 ;;
    --reason-output) reason_output="$2"; shift 2 ;;
    --changed-files) shift 2 ;;
    *) shift ;;
  esac
done
: > "$output"
i=0
while [ "$i" -lt "${STUB_SELECTED_COUNT:-0}" ]; do
  printf 'tests/selector_%03d_test.py\n' "$i" >> "$output"
  i=$((i + 1))
done
printf '%s\n' "${STUB_REASON:-broad selector fallout}" > "$reason_output"
STUB
chmod +x "$WORK/fake-python"

mkdir -p "$WORK/repo/backend/tests" "$WORK/repo/backend/scripts"
touch "$WORK/repo/backend/scripts/select_backend_unit_tests.py"
cat > "$WORK/repo/backend/test-preflight.sh" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
cat > "$WORK/repo/backend/test.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
wc -l < "$BACKEND_UNIT_TEST_FILE_LIST" | tr -d ' ' > "$RAN_COUNT_FILE"
cp "$BACKEND_UNIT_TEST_FILE_LIST" "$RAN_LIST_FILE"
STUB

# $1 = changed suffix-style tests, $2 = cap, $3 = include helpers and a nested test
run_case() {
  local changed_test_files="$1" cap="$2" include_helpers="${3:-0}" i
  rm -f "$WORK/ran_count" "$WORK/ran_list"
  rm -f "$WORK/repo/backend/tests/"*.py
  local -a changed=()
  for ((i = 0; i < changed_test_files; i++)); do
    printf -v name 'backend/tests/changed_%03d_test.py' "$i"
    touch "$WORK/repo/$name"
    changed+=("$name")
  done
  if [ "$include_helpers" = 1 ]; then
    mkdir -p "$WORK/repo/backend/tests/support" "$WORK/repo/backend/tests/unit"
    for name in backend/tests/support/lifecycle_state_table.py backend/tests/support/__init__.py backend/tests/unit/conftest.py; do
      touch "$WORK/repo/$name"
      changed+=("$name")
    done
    if [ "$changed_test_files" -gt 0 ]; then
      name=backend/tests/unit/test_nested.py
      touch "$WORK/repo/$name"
      changed+=("$name")
    fi
  fi

  (
    cd "$WORK/repo"
    # shellcheck disable=SC2034
    CHANGED_FILES=("${changed[@]+"${changed[@]}"}" "backend/app.py")
    BACKEND_PYTHON="$WORK/fake-python"
    CHANGED_FILES_LIST="$WORK/changed"
    SELECTED_BACKEND_TESTS="$WORK/selected"
    SELECTED_BACKEND_TESTS_REASON="$WORK/reason"
    FAST_BACKEND_TESTS="$WORK/fast"
    PRE_PUSH_MAX_BACKEND_UNIT_TEST_FILES="$cap"
    export RAN_COUNT_FILE="$WORK/ran_count" RAN_LIST_FILE="$WORK/ran_list"
    printf '%s\n' "${CHANGED_FILES[@]}" > "$CHANGED_FILES_LIST"
    : > "$SELECTED_BACKEND_TESTS"
    : > "$SELECTED_BACKEND_TESTS_REASON"
    : > "$FAST_BACKEND_TESTS"
    changed_matches() { return 0; }
    require_backend_python() { :; }
    # shellcheck source=/dev/null
    source "$FUNC"
    check_backend_unit_tests_if_needed
  )
}

CAP=10
export STUB_SELECTED_COUNT=500 STUB_REASON="broad selector fallout"

# Regression (#11018 class): a diff whose own changed backend test files exceed
# the cap must still run at most the cap. Before the bound this ran all 25.
output="$(run_case 25 "$CAP")"
ran="$(cat "$WORK/ran_count")"
if [ "$ran" -gt "$CAP" ]; then
  echo "FAIL: fallback ran $ran backend test file(s), over the cap of $CAP" >&2
  echo "$output" >&2
  exit 1
fi
case "$output" in
  *"cap is $CAP"*)
    echo "FAIL: message advertises a cap the run may exceed instead of reporting the truncation" >&2
    echo "$output" >&2
    exit 1
    ;;
esac
grep -q "25 backend test file(s), also over the cap of $CAP" <<<"$output" || {
  echo "FAIL: message does not report requested vs actual counts" >&2; echo "$output" >&2; exit 1; }
grep -q "Running the first $ran in sorted order" <<<"$output" || {
  echo "FAIL: message does not report what actually ran" >&2; echo "$output" >&2; exit 1; }

# Truncation is deterministic: the same diff selects the same files every push.
first_list="$(cat "$WORK/ran_list")"
run_case 25 "$CAP" >/dev/null
test "$first_list" = "$(cat "$WORK/ran_list")" || {
  echo "FAIL: truncated selection is not stable across runs" >&2; exit 1; }
test "$first_list" = "$(sort "$WORK/ran_list")" || {
  echo "FAIL: truncated selection is not sorted" >&2; exit 1; }

# Under the cap the existing fallback behavior is unchanged.
output="$(run_case 4 "$CAP")"
test "$(cat "$WORK/ran_count")" = "4"
grep -q "running 4 changed backend test file(s) instead; cap is $CAP" <<<"$output" || {
  echo "FAIL: under-cap fallback message regressed" >&2; echo "$output" >&2; exit 1; }

# No changed backend test files still skips the broad suite entirely.
output="$(run_case 0 "$CAP")"
test ! -f "$WORK/ran_count"
grep -q "Skipping broad backend unit suite in pre-push" <<<"$output" || {
  echo "FAIL: empty fallback no longer skips" >&2; echo "$output" >&2; exit 1; }

# A helper edit still requires CI's broad selector, but is not itself a test file.
# Both standard pytest filename forms must survive while support/conftest do not.
output="$(run_case 3 "$CAP" 1)"
test "$(cat "$WORK/ran_count")" = 4
grep -qx 'tests/unit/test_nested.py' "$WORK/ran_list"
grep -qx 'tests/changed_002_test.py' "$WORK/ran_list"
if grep -Eq '(^|/)(conftest|__init__|lifecycle_state_table)\.py$' "$WORK/ran_list"; then
  echo "FAIL: fallback selected a helper as a standalone pytest file" >&2
  exit 1
fi
output="$(run_case 0 "$CAP" 1)"
test ! -f "$WORK/ran_count"
grep -q "Skipping broad backend unit suite in pre-push" <<<"$output"

echo "pre-push backend unit test cap tests passed"
