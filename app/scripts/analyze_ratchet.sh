#!/usr/bin/env bash
# Dart analyzer ratchet for app/.
#
# Contract:
#   - Any ERROR severity diagnostic always fails the build and is never
#     baselined (undefined methods, wrong argument types, broken imports,
#     etc. must never be silently accepted). Verified empirically: dart
#     analyze reports these as COMPILE_TIME_ERROR/ERROR, distinct from the
#     WARNING-severity diagnostics below.
#   - WARNING and INFO level diagnostics are ratcheted together: the script
#     counts occurrences PER RULE across the whole app/ tree (not per file,
#     by design — this tracks total occurrences of a rule so moving/renaming
#     files doesn't trip false positives) and compares against the committed
#     baseline in analysis_baseline.json. A rule may not regress above its
#     baseline count; rules with fewer occurrences than baseline are reported
#     as an improvement opportunity but do not fail the build.
#   - Fail closed on analyzer crash: if dart analyze exits non-zero without
#     producing a single machine-format diagnostic line, the invocation
#     itself failed (crash, bad SDK, unparseable output) and the script
#     exits 1 instead of treating the empty output as "zero issues". The
#     check is structural (nonzero exit + zero parseable diagnostics), not
#     tied to specific exit codes, which vary across Dart versions. A clean
#     run (exit 0, no diagnostics) still passes.
#
#   Deviation from the original design note ("ERROR or WARNING always
#   fails"): dart analyze on this codebase currently reports 138 pre-existing
#   WARNING-severity diagnostics (unused_import, dead_null_aware_expression,
#   unnecessary_non_null_assertion, etc. — style/dead-code issues, not broken
#   builds), not zero as assumed. Hard-failing on WARNING unconditionally
#   would make this gate permanently red on unrelated PRs and require fixing
#   pre-existing lint debt out of scope. Genuine broken-code diagnostics
#   (undefined methods, wrong argument types, broken imports) are ERROR
#   severity, not WARNING — so ERROR-only hard-fail preserves the intended
#   safety property while WARNING rides the same ratchet as INFO.
#
# Usage:
#   app/scripts/analyze_ratchet.sh                  # check against baseline
#   app/scripts/analyze_ratchet.sh --update-baseline # regenerate baseline
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

BASELINE_FILE="analysis_baseline.json"
UPDATE_BASELINE=false

for arg in "$@"; do
  case "$arg" in
    --update-baseline)
      UPDATE_BASELINE=true
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

required_files=(
  "lib/env/dev_env.g.dart"
  "lib/firebase_options_dev.dart"
)
missing_files=()
for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    missing_files+=("$file")
  fi
done
if [[ ${#missing_files[@]} -gt 0 ]]; then
  echo "Generated files missing — run \`bash app/test.sh\` once (or the setup in app/test.sh) before analyzing." >&2
  echo "Missing: ${missing_files[*]}" >&2
  exit 1
fi

echo "Running: dart analyze --format=machine ."
# dart analyze exits non-zero whenever it finds any issue (info included),
# so capture output without letting set -e kill the script on that line.
set +e
ANALYZE_OUTPUT=$(dart analyze --format=machine . 2>&1)
ANALYZE_EXIT=$?
set -e

# Machine format is pipe-delimited:
#   SEVERITY|TYPE|RULE|FILE|LINE|COLUMN|LENGTH|MESSAGE

# Fail closed on analyzer crash: a nonzero exit with zero parseable
# machine-format lines means the analyzer invocation itself failed, not that
# the tree is clean. Don't check specific exit codes — they vary across Dart
# versions; the structural check is the contract. Count with awk rather than
# grep -q: under pipefail, grep -q exits at the first match and printf takes
# a SIGPIPE on large outputs, turning a healthy run into a false failure.
PARSEABLE_COUNT=$(printf '%s\n' "$ANALYZE_OUTPUT" | awk '/^(ERROR|WARNING|INFO)\|/ { n++ } END { print n + 0 }')
if [[ $ANALYZE_EXIT -ne 0 && $PARSEABLE_COUNT -eq 0 ]]; then
  echo "" >&2
  echo "dart analyze did not produce parseable results — failing closed." >&2
  echo "Exit code: $ANALYZE_EXIT" >&2
  echo "Raw output:" >&2
  printf '%s\n' "$ANALYZE_OUTPUT" >&2
  exit 1
fi

SEVERE_LINES=$(printf '%s\n' "$ANALYZE_OUTPUT" | awk -F'|' '$1 == "ERROR"')
if [[ -n "$SEVERE_LINES" ]]; then
  echo ""
  echo "Error-severity diagnostics found (never baselined):"
  printf '%s\n' "$SEVERE_LINES"
  exit 1
fi

# WARNING and INFO level diagnostics: exclude generated files (build_runner
# outputs and lib/l10n/), then count remaining occurrences per rule.
CURRENT_JSON=$(printf '%s\n' "$ANALYZE_OUTPUT" | awk -F'|' '
  $1 == "WARNING" || $1 == "INFO" {
    file = $4
    if (file ~ /\.g\.dart$/ || file ~ /\.gen\.dart$/ || file ~ /\.freezed\.dart$/ || file ~ /\/lib\/l10n\//) next
    rule = tolower($3)
    counts[rule]++
  }
  END {
    printf "{"
    first = 1
    for (r in counts) {
      if (!first) printf ","
      printf "\"%s\":%d", r, counts[r]
      first = 0
    }
    printf "}"
  }
')
CURRENT_JSON=$(echo "$CURRENT_JSON" | jq -S '.')

if $UPDATE_BASELINE; then
  echo "$CURRENT_JSON" | jq -S '.' > "$BASELINE_FILE"
  echo "Updated $BASELINE_FILE from the current analyzer run."
  exit 0
fi

if [[ ! -f "$BASELINE_FILE" ]]; then
  echo "$BASELINE_FILE not found. Run with --update-baseline to create it." >&2
  exit 1
fi

FAILED=false
ALL_RULES=$( { jq -r 'keys[]' <<<"$CURRENT_JSON"; jq -r 'keys[]' "$BASELINE_FILE"; } | sort -u)

while IFS= read -r rule; do
  [[ -z "$rule" ]] && continue
  current=$(jq -r --arg r "$rule" '.[$r] // 0' <<<"$CURRENT_JSON")
  baseline=$(jq -r --arg r "$rule" '.[$r] // 0' "$BASELINE_FILE")
  if (( current > baseline )); then
    echo "$rule: $current found, baseline $baseline — fix the new occurrences"
    FAILED=true
  elif (( current < baseline )); then
    echo "$rule: improved ($current found, baseline $baseline) — consider running --update-baseline to lock in"
  fi
done <<<"$ALL_RULES"

if $FAILED; then
  echo ""
  echo "Analyzer ratchet failed. Deliberate acceptances require running:"
  echo "  app/scripts/analyze_ratchet.sh --update-baseline"
  echo "in the same PR."
  exit 1
fi

echo "Analyzer ratchet passed."
