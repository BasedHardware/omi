#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT="$MACOS_DIR/scripts/check-e2e-flow-coverage.py"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

mkdir -p "$TMPDIR/desktop/macos/e2e/flows"
cat >"$TMPDIR/desktop/macos/e2e/flows/chat.yaml" <<'YAML'
version: 2
name: chat
covers:
  - desktop/Desktop/Sources/MainWindow/Pages/ChatPage.swift
YAML

covered="desktop/macos/Desktop/Sources/MainWindow/Pages/ChatPage.swift"
uncovered="desktop/macos/Desktop/Sources/MainWindow/Pages/UncoveredPage.swift"

if ! "$SCRIPT" --root "$TMPDIR" "$covered" "$uncovered" >"$TMPDIR/report.out" 2>"$TMPDIR/report.err"; then
  fail "advisory coverage check unexpectedly failed"
fi
grep -q "COVERED   $covered -> chat (chat.yaml)" "$TMPDIR/report.out" || fail "covered file was not reported"
grep -q "UNCOVERED $uncovered" "$TMPDIR/report.out" || fail "uncovered file was not reported"
grep -q "OMI_APP_NAME=omi-e2e ./scripts/omi-harness run e2e/flows/chat.yaml" "$TMPDIR/report.out" || \
  fail "recommended harness command missing"

if "$SCRIPT" --root "$TMPDIR" --strict "$covered" "$uncovered" >"$TMPDIR/strict.out" 2>"$TMPDIR/strict.err"; then
  fail "strict coverage check unexpectedly passed with an uncovered file"
fi
grep -q "FAIL: uncovered changed desktop Swift files found" "$TMPDIR/strict.err" || fail "strict failure was not explained"

echo "e2e flow coverage tests passed"
