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
grep -q "./scripts/desktop-core-harness.sh --tier 2 --bundle omi-core-e2e --port <automation-port> --keep-stack" "$TMPDIR/report.out" || \
  fail "recommended harness command missing"

if "$SCRIPT" --root "$TMPDIR" --strict "$covered" "$uncovered" >"$TMPDIR/strict.out" 2>"$TMPDIR/strict.err"; then
  fail "strict coverage check unexpectedly passed with an uncovered file"
fi
grep -q "FAIL: uncovered changed desktop Swift files found" "$TMPDIR/strict.err" || fail "strict failure was not explained"

REPO="$TMPDIR/repo"
mkdir -p "$REPO/desktop/macos/e2e/flows" "$REPO/desktop/macos/Desktop/Sources/MainWindow/Pages"
repo_git() {
  env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE git -C "$REPO" "$@"
}
repo_git init -q
repo_git config user.email "desktop-tests@example.com"
repo_git config user.name "Desktop Tests"
repo_git config core.hooksPath /dev/null

cat >"$REPO/desktop/macos/e2e/flows/chat.yaml" <<'YAML'
version: 2
name: chat
covers:
  - desktop/Desktop/Sources/MainWindow/Pages/ChatPage.swift
YAML
echo "old" >"$REPO/desktop/macos/Desktop/Sources/MainWindow/Pages/StaleMainOnly.swift"
repo_git add .
repo_git commit -q -m "old origin main"
repo_git branch origin/main

echo "fresh" >"$REPO/desktop/macos/Desktop/Sources/MainWindow/Pages/StaleMainOnly.swift"
repo_git commit -q -am "fresh upstream main"
repo_git branch upstream/main

repo_git checkout -q -b feature
echo "feature" >"$REPO/desktop/macos/Desktop/Sources/MainWindow/Pages/ChatPage.swift"
repo_git add .
repo_git commit -q -m "feature change"

if ! "$SCRIPT" --root "$REPO" --strict >"$TMPDIR/stale-ref.out" 2>"$TMPDIR/stale-ref.err"; then
  cat "$TMPDIR/stale-ref.out"
  cat "$TMPDIR/stale-ref.err" >&2
  fail "strict coverage check should use the closest main ref when origin/main is stale"
fi
grep -q "Changed desktop Swift files: 1" "$TMPDIR/stale-ref.out" || \
  fail "stale origin/main caused unrelated upstream changes to be counted"
grep -q "COVERED   desktop/macos/Desktop/Sources/MainWindow/Pages/ChatPage.swift" "$TMPDIR/stale-ref.out" || \
  fail "feature change was not checked against e2e coverage"
if grep -q "StaleMainOnly.swift" "$TMPDIR/stale-ref.out"; then
  fail "stale origin/main-only file appeared in coverage report"
fi

POISONED_GIT_DIR="$(git -C "$MACOS_DIR/../.." rev-parse --git-dir 2>/dev/null || true)"
if [ -n "$POISONED_GIT_DIR" ]; then
  if ! env GIT_DIR="$POISONED_GIT_DIR" "$SCRIPT" --root "$REPO" --strict >"$TMPDIR/poisoned-env.out" 2>"$TMPDIR/poisoned-env.err"; then
    cat "$TMPDIR/poisoned-env.out"
    cat "$TMPDIR/poisoned-env.err" >&2
    fail "strict coverage check should ignore inherited Git environment"
  fi
  grep -q "Changed desktop Swift files: 1" "$TMPDIR/poisoned-env.out" || \
    fail "inherited Git environment caused unrelated changes to be counted"
  grep -q "COVERED   desktop/macos/Desktop/Sources/MainWindow/Pages/ChatPage.swift" "$TMPDIR/poisoned-env.out" || \
    fail "inherited Git environment prevented feature change coverage detection"
fi

echo "e2e flow coverage tests passed"
