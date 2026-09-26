#!/usr/bin/env bash
# Run the `slow`-marked backend guardrails that `run-unit-ci.sh` excludes.
#
# `run-unit-ci.sh` runs `not integration and not slow`, which is right for the
# PR latency budget but left every codebase-grep guardrail in the repository
# executing nowhere. This lane runs exactly those tests, for the files listed in
# tests/slow_guardrail_manifest.txt, and nothing else.
#
# Deliberately NOT file-isolated: these are static scans that import little, and
# one session over the whole manifest is what keeps the lane under two minutes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
cd "$BACKEND_DIR"

PYTHON_BIN="${PYTHON:-python}"
MANIFEST="tests/slow_guardrail_manifest.txt"

if [ ! -f "$MANIFEST" ]; then
  echo "FAIL: $MANIFEST is missing; the guardrail lane cannot silently run nothing." >&2
  exit 1
fi

files=()
while IFS= read -r line; do
  line="${line%%#*}"
  line="$(printf '%s' "$line" | tr -d '[:space:]')"
  [ -n "$line" ] || continue
  if [ ! -f "$line" ]; then
    echo "FAIL: $MANIFEST lists $line, which does not exist." >&2
    exit 1
  fi
  files+=("$line")
done < "$MANIFEST"

if [ "${#files[@]}" -eq 0 ]; then
  echo "FAIL: $MANIFEST selected no files; a lane that runs nothing passes for the wrong reason." >&2
  exit 1
fi

echo "Running slow-marked guardrails across ${#files[@]} file(s)."
exec "$PYTHON_BIN" -m pytest -q -p no:cacheprovider -m "slow and not integration" "${files[@]}"
