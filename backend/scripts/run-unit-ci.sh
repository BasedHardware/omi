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
# loaded shard using measured per-file WALL weights
# (backend_unit_shard_weights.tsv; unlisted files weigh DEFAULT_WEIGHT);
# each shard's slice keeps that deal order, so test.sh's worker slots run a
# longest-processing-time schedule instead of launching heavy files late in
# alphabetical order (PR #23767: round-robin left shard walls 433-754s; the
# 2026-10-27 rebuild prices import/collection startup, which the old
# pytest-time table missed on a 183s and a 130s file). Without weights every
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
# Decide the type-check boundary once, BEFORE the deal, so the deal reserves
# shard 1's capacity exactly when shard 1 will actually pay the check (a
# changed-files run whose paths do not affect the typed boundary typechecks
# nowhere and must not hand shard 1's capacity to its siblings).
will_typecheck=1
if [ "$mode" != "--all" ] && ! "$SCRIPT_DIR/needs-typecheck.sh" "$changed_files_arg"; then
  will_typecheck=0
fi
if [ "$shard_total" -ge 2 ]; then
  full_count="$(wc -l < "$selected_tests" | tr -d ' ')"
  sliced="$(mktemp "${TMPDIR:-/tmp}/omi-backend-unit-tests-shard.XXXXXX")"
  # One-based shard labels; ties break on fewest files, then lowest shard.
  "$PYTHON_BIN" - "$selected_tests" "$shard_total" "$shard_index" "$SCRIPT_DIR/backend_unit_shard_weights.tsv" "$will_typecheck" \
    >"$sliced" <<'PY'
import os
import sys

DEFAULT_WEIGHT = 1.66  # mean measured wall seconds of the files below the table's 2s floor
# (p90-wall table, 20 main runs to 2026-10-27; the old 1.1 priced pytest time
# only and undercharged per-file import/collection startup)
selection, total, shard, table, will_typecheck = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5] == '1'
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
# Only shard 1 runs the type check when CI fans out (see below): its ~90s of
# fixed pre-test wall is charged to shard 1's load here (x4 because a shard's
# wall is its load spread over 4 worker lanes) so every shard finishes level.
if total >= 2 and will_typecheck:
    load[0] += 360.0
# deal order is also the slice order: test.sh launches files in list order
# into its worker slots, so heaviest-first turns that scheduler into LPT and
# keeps one heavy file from serializing a shard's tail (the alphabetical
# order let a 183s file start 75% into its shard and cap the lane for the
# whole final quarter; PR #23789 shard 3, 724s wall).
deal_order = sorted(paths, key=lambda path: (-weight[path], path))
for path in deal_order:
    target = min(range(total), key=lambda index: (load[index], count[index], index))
    load[target] += weight[path]
    count[target] += 1
    assigned[path] = target + 1
for path in deal_order:
    if assigned[path] == shard:
        print(path)
PY
  mv "$sliced" "$selected_tests"
  shard_note=" (shard ${shard_index}/${shard_total}: $(wc -l < "$selected_tests" | tr -d ' ') of ${full_count} files)"
fi

selected_count="$(wc -l < "$selected_tests" | tr -d ' ')"
reason="$(cat "$selection_reason")"

# Preflight runs in every shard: it is seconds of work, and keeping the
# runner's phases identical across shards means a shard cannot silently lose
# a guard its siblings ran. The full-tree type check is different: it is
# deterministic over the identical checkout every shard sees, so when CI fans
# out only shard 1 pays its ~90s; its failure still fails the whole workflow
# run for that commit exactly as before (2026-10-27: six shards each paid
# ~99s of pre-test wall for the same pyright result, ~8m of runner time per
# main commit and ~99s of every shard's 720s budget).
PYTHON="$PYTHON_BIN" bash test-preflight.sh
if [ "$will_typecheck" -eq 1 ]; then
  if [ "$shard_total" -lt 2 ] || [ "$shard_index" -eq 1 ]; then
    PYTHON="$PYTHON_BIN" bash scripts/typecheck.sh
  else
    echo "Skipping backend type check on shard ${shard_index}/${shard_total}: shard 1 runs it for this commit."
  fi
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
