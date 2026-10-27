#!/usr/bin/env bash
# Run the full backend unit-test contract used by GitHub Actions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_DIR"

usage() {
  echo "usage: $0 [--all | --changed-files <repo-relative-path-list>] [--shard <total>/<index>]" >&2
  exit 2
}

mode=""
changed_files_arg=""
shard_spec=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --all)
      [ -z "$mode" ] || usage
      mode="--all"
      ;;
    --changed-files)
      [ -z "$mode" ] && [ "$#" -ge 2 ] && [ -f "$2" ] || usage
      mode="--changed-files"
      changed_files_arg="$2"
      shift
      ;;
    --shard)
      [ "$#" -ge 2 ] || usage
      shard_spec="$2"
      shift
      ;;
    *)
      usage
      ;;
  esac
  shift
done
[ -n "$mode" ] || usage

# Sharding: the suite's cost is per-file pytest process startup (measured
# 2026-09-10, run 34430370667: 1126 files, one session each, 19m18s of a
# 21m53s run, while only two files exceeded 4.5s of test time), and sharing
# one pytest process across files is blocked by dense sys.modules
# contamination (see the BACKEND_PYTEST_PARALLEL_SESSION measurement in
# test.sh). CI therefore fans the SAME selection out to N parallel jobs;
# each shard computes the same deterministic partition of the sorted file
# list, so the union of the shards is exactly the full selection and every
# file keeps its own process. Files are dealt heaviest-first to the least
# loaded shard using measured per-file weights (backend_unit_shard_weights.tsv;
# unlisted files weigh DEFAULT_WEIGHT). A round-robin slice let one inserted
# file shift every later file and left shard walls 433-754s on PR #23767; in
# leave-one-run-out checks over three full-suite runs the weighted deal cut
# the worst projected shard from 725-757s to 653-708s. Without weights every
# file ties and the deal is round-robin.
shard_total=0
shard_index=0
if [ -n "$shard_spec" ]; then
  case "$shard_spec" in
    */*) ;;
    *) usage ;;
  esac
  shard_total="${shard_spec%%/*}"
  shard_index="${shard_spec##*/}"
  [[ "$shard_total" =~ ^[0-9]+$ ]] && [ "$shard_total" -ge 1 ] || usage
  [[ "$shard_index" =~ ^[0-9]+$ ]] && [ "$shard_index" -ge 1 ] && [ "$shard_index" -le "$shard_total" ] || usage
fi

PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x .venv/bin/python ]; then
    PYTHON_BIN=.venv/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

selected_tests="$(mktemp "${TMPDIR:-/tmp}/omi-backend-unit-tests.XXXXXX")"
selection_reason="$(mktemp "${TMPDIR:-/tmp}/omi-backend-unit-tests-reason.XXXXXX")"
trap 'rm -f "$selected_tests" "$selection_reason"' EXIT

selector_args=(--output "$selected_tests" --reason-output "$selection_reason")
if [ "$mode" = "--all" ]; then
  selector_args+=(--all)
else
  selector_args+=(--changed-files "$changed_files_arg")
fi
"$PYTHON_BIN" scripts/select_backend_unit_tests.py "${selector_args[@]}"

shard_note=""
if [ "$shard_total" -ge 2 ]; then
  full_count="$(wc -l < "$selected_tests" | tr -d ' ')"
  sliced="$(mktemp "${TMPDIR:-/tmp}/omi-backend-unit-tests-shard.XXXXXX")"
  # One-based shard labels; ties break on fewest files, then lowest shard.
  "$PYTHON_BIN" - "$selected_tests" "$shard_total" "$shard_index" "$SCRIPT_DIR/backend_unit_shard_weights.tsv" \
    >"$sliced" <<'PY'
import os
import sys

DEFAULT_WEIGHT = 1.1  # mean measured seconds of the files below the table's 2s floor
selection, total, shard, table = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
with open(selection, encoding='utf-8') as handle:
    paths = [line.rstrip('\n') for line in handle if line.strip()]
measured = {}
if os.path.isfile(table):
    with open(table, encoding='utf-8') as handle:
        for line in handle:
            if line.strip() and not line.startswith('#'):
                path, seconds = line.rstrip('\n').split('\t')
                measured[path] = float(seconds)
weight = {path: measured.get(path, DEFAULT_WEIGHT) for path in paths}
load, count, assigned = [0.0] * total, [0] * total, {}
for path in sorted(paths, key=lambda path: (-weight[path], path)):
    target = min(range(total), key=lambda index: (load[index], count[index], index))
    load[target] += weight[path]
    count[target] += 1
    assigned[path] = target + 1
for path in paths:
    if assigned[path] == shard:
        print(path)
PY
  mv "$sliced" "$selected_tests"
  shard_note=" (shard ${shard_index}/${shard_total}: $(wc -l < "$selected_tests" | tr -d ' ') of ${full_count} files)"
fi

selected_count="$(wc -l < "$selected_tests" | tr -d ' ')"
reason="$(cat "$selection_reason")"

# Preflight and the typecheck boundary decision run in every shard: they are
# seconds of work, and keeping the runner's phases identical across shards
# means a shard cannot silently lose a guard its siblings ran.
PYTHON="$PYTHON_BIN" bash test-preflight.sh
if [ "$mode" = "--all" ] || "$SCRIPT_DIR/needs-typecheck.sh" "$changed_files_arg"; then
  PYTHON="$PYTHON_BIN" bash scripts/typecheck.sh
else
  echo "Skipping backend type check: changed paths do not affect the typed boundary."
fi

if [ "$selected_count" -eq 0 ]; then
  echo "No backend unit tests selected${shard_note}: $reason"
  exit 0
fi

echo "Selected $selected_count backend unit test file(s)${shard_note}: $reason"
BACKEND_UNIT_TEST_FILE_LIST="$selected_tests" \
BACKEND_FAST_UNIT_WARN_SECONDS="0.1" \
BACKEND_FAST_UNIT_FAIL_SECONDS="1.0" \
BACKEND_PYTEST_FILE_ISOLATION="1" \
BACKEND_PYTEST_MARK_EXPR="not integration and not slow" \
BACKEND_PYTEST_XDIST="auto" \
BACKEND_PYTEST_WORKERS="auto" \
PYTHON="$PYTHON_BIN" \
bash test.sh
