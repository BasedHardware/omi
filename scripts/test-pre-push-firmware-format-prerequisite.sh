#!/usr/bin/env bash
set -euo pipefail

# Behavioral regression for the formatter prerequisite deferred in #12993.
# Source the actual hook branch into a controlled fixture so this verifies
# process execution and exit status rather than matching hook diagnostics.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
fixture_mode="${1:-}"
unset FORMATTER_ARGS FORMATTER_EXIT FORMATTER_FUNCTION PRE_PUSH_SKIP_FIRMWARE_FORMAT

# The fixture is selected by pre-push and must not let a caller's formatter
# test variables redirect the sourced function or change its expected result.
if [ "$fixture_mode" != "--hostile-env-probe" ]; then
  FORMATTER_ARGS=/dev/null \
    FORMATTER_EXIT=97 \
    FORMATTER_FUNCTION=/dev/null \
    bash "${BASH_SOURCE[0]}" --hostile-env-probe >/dev/null
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/omi-pre-push-firmware-format.XXXXXX")"
trap 'rm -rf "$FIXTURE_TMP"' EXIT

FUNCTION="$FIXTURE_TMP/check_firmware_formatters.sh"
awk '/^check_firmware_formatters\(\) \{$/,/^\}$/' "$ROOT/scripts/pre-push" >"$FUNCTION"
if ! grep -qx '}' "$FUNCTION"; then
  echo "FAIL: could not extract check_firmware_formatters from scripts/pre-push" >&2
  exit 1
fi

mkdir -p "$FIXTURE_TMP/repo/omi/firmware" "$FIXTURE_TMP/repo/omiGlass/firmware" "$FIXTURE_TMP/repo/docs" "$FIXTURE_TMP/bin" "$FIXTURE_TMP/no-formatter"
printf 'int main(void) { return 0; }\n' >"$FIXTURE_TMP/repo/omi/firmware/fixture.c"
printf '#pragma once\n' >"$FIXTURE_TMP/repo/omiGlass/firmware/fixture.hpp"
printf 'fixture\n' >"$FIXTURE_TMP/repo/docs/fixture.md"

cat >"$FIXTURE_TMP/bin/clang-format" <<'EOF'
#!/bin/sh
: "${FORMATTER_ARGS:?FORMATTER_ARGS is required}"
printf '%s\n' "$@" >"$FORMATTER_ARGS"
exit "${FORMATTER_EXIT:-0}"
EOF
chmod +x "$FIXTURE_TMP/bin/clang-format"

run_formatter_check() (
  cd "$FIXTURE_TMP/repo"
  CHANGED_FILES=("$@")
  ci_prediction_note_skipped() { : >"$SKIP_MARKER"; }
  # shellcheck source=/dev/null
  source "${FORMATTER_FUNCTION:-$FUNCTION}"
  check_firmware_formatters
)

# The assertion is expressed as behavior so the temporary legacy mutant below
# can prove that the fixture would reject the old silent-pass branch.
missing_formatter_must_fail() {
  local function_file="$1"
  if PATH="$FIXTURE_TMP/no-formatter" FORMATTER_FUNCTION="$function_file" run_formatter_check omi/firmware/fixture.c >/dev/null 2>&1; then
    return 1
  fi
}

# A selected firmware path must fail when no formatter can be resolved.
missing_formatter_must_fail "$FUNCTION"

# Restore the legacy no-op in a temporary extracted function. This must make
# the missing-formatter assertion fail, proving the fixture is sensitive to
# the historical silent pass instead of only the helper's presence.
LEGACY_SKIP_FUNCTION="$FIXTURE_TMP/check_firmware_formatters-legacy-skip.sh"
awk '
  /^  else$/ { print; print "    :"; skipping = 1; next }
  skipping && /^  fi$/ { print; skipping = 0; next }
  !skipping { print }
' "$FUNCTION" >"$LEGACY_SKIP_FUNCTION"
if missing_formatter_must_fail "$LEGACY_SKIP_FUNCTION"; then
  echo "FAIL: missing-formatter fixture did not detect the legacy silent pass" >&2
  exit 1
fi

# A formatter on PATH must receive the hook's dry-run/Werror invocation and
# every selected firmware source, including the legacy omiGlass tree.
FORMATTER_ARGS="$FIXTURE_TMP/formatter-args"
export FORMATTER_ARGS
PATH="$FIXTURE_TMP/bin" run_formatter_check omi/firmware/fixture.c omiGlass/firmware/fixture.hpp >/dev/null
expected_args="$FIXTURE_TMP/expected-formatter-args"
printf '%s\n' --dry-run --Werror omi/firmware/fixture.c omiGlass/firmware/fixture.hpp >"$expected_args"
if ! cmp -s "$expected_args" "$FORMATTER_ARGS"; then
  echo "FAIL: pre-push did not invoke clang-format with the selected firmware files" >&2
  exit 1
fi

# Formatter failures must propagate instead of being reported as a successful
# pre-push formatting check.
FORMATTER_EXIT=23
export FORMATTER_EXIT
if PATH="$FIXTURE_TMP/bin" run_formatter_check omi/firmware/fixture.c >/dev/null 2>&1; then
  echo "FAIL: clang-format failure did not fail pre-push" >&2
  exit 1
fi
unset FORMATTER_EXIT

# The deliberate formatter hatch must take the bypass visibly, so the hook's
# bounded CI-prediction summary cannot look like a verified format check.
SKIP_MARKER="$FIXTURE_TMP/firmware-format-skipped"
export SKIP_MARKER
PRE_PUSH_SKIP_FIRMWARE_FORMAT=1 PATH="$FIXTURE_TMP/no-formatter" run_formatter_check omi/firmware/fixture.c >/dev/null
if [ ! -e "$SKIP_MARKER" ]; then
  echo "FAIL: firmware-format hatch did not record a skipped formatter check" >&2
  exit 1
fi

# A deleted firmware source and a non-firmware push must stay independent of
# an unprovisioned formatter.
PATH="$FIXTURE_TMP/no-formatter" run_formatter_check omi/firmware/deleted.c >/dev/null
rm -f "$FORMATTER_ARGS"
PATH="$FIXTURE_TMP/no-formatter" run_formatter_check docs/fixture.md >/dev/null
if [ -e "$FORMATTER_ARGS" ]; then
  echo "FAIL: non-firmware path invoked clang-format" >&2
  exit 1
fi

echo "pre-push firmware formatter prerequisite tests passed"
