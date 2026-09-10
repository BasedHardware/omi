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
# each shard executes an interleaved slice of the deterministic, sorted
# file list, so slow files spread across shards and the union of the
# shards is exactly the full selection (line i runs in shard
# ((i-1) % total)+1, and every file keeps its own process).
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
  # NB: `index` is an awk builtin, so the shard variable must be named
  # anything else; passing -v index=… is a syntax error on every awk.
  awk -v total="$shard_total" -v shard="$shard_index" 'NR % total == (shard - 1) % total' \
    "$selected_tests" >"$sliced"
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
