#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT="$MACOS_DIR/scripts/check-e2e-flow-coverage.py"

coverage_check() {
  "$SCRIPT" --formatter-binary none "$@"
}

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

if ! coverage_check --root "$TMPDIR" "$covered" "$uncovered" >"$TMPDIR/report.out" 2>"$TMPDIR/report.err"; then
  fail "advisory coverage check unexpectedly failed"
fi
grep -q "COVERED   $covered -> chat (chat.yaml)" "$TMPDIR/report.out" || fail "covered file was not reported"
grep -q "UNCOVERED $uncovered" "$TMPDIR/report.out" || fail "uncovered file was not reported"
grep -q "./scripts/desktop-core-harness.sh --tier 2 --bundle omi-core-e2e --port <automation-port> --keep-stack" "$TMPDIR/report.out" || \
  fail "recommended harness command missing"

if coverage_check --root "$TMPDIR" --strict "$covered" "$uncovered" >"$TMPDIR/strict.out" 2>"$TMPDIR/strict.err"; then
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
echo 'let value = 1' >"$REPO/desktop/macos/Desktop/Sources/MainWindow/Pages/FormatterOnly.swift"
echo 'let value = "same"' >"$REPO/desktop/macos/Desktop/Sources/MainWindow/Pages/LiteralWhitespace.swift"
repo_git add .
repo_git commit -q -m "fresh upstream main"
repo_git branch upstream/main

repo_git checkout -q -b feature
echo "feature" >"$REPO/desktop/macos/Desktop/Sources/MainWindow/Pages/ChatPage.swift"
echo 'let value=1' >"$REPO/desktop/macos/Desktop/Sources/MainWindow/Pages/FormatterOnly.swift"
repo_git add .
repo_git commit -q -m "feature change"

if ! coverage_check --root "$REPO" --strict >"$TMPDIR/stale-ref.out" 2>"$TMPDIR/stale-ref.err"; then
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
if grep -q "FormatterOnly.swift" "$TMPDIR/stale-ref.out"; then
  fail "formatter-only Swift source was not excluded from coverage"
fi

POISONED_GIT_DIR="$(git -C "$MACOS_DIR/../.." rev-parse --git-dir 2>/dev/null || true)"
if [ -n "$POISONED_GIT_DIR" ]; then
  if ! GIT_DIR="$POISONED_GIT_DIR" coverage_check --root "$REPO" --strict >"$TMPDIR/poisoned-env.out" 2>"$TMPDIR/poisoned-env.err"; then
    cat "$TMPDIR/poisoned-env.out"
    cat "$TMPDIR/poisoned-env.err" >&2
    fail "strict coverage check should ignore inherited Git environment"
  fi
  grep -q "Changed desktop Swift files: 1" "$TMPDIR/poisoned-env.out" || \
    fail "inherited Git environment caused unrelated changes to be counted"
  grep -q "COVERED   desktop/macos/Desktop/Sources/MainWindow/Pages/ChatPage.swift" "$TMPDIR/poisoned-env.out" || \
    fail "inherited Git environment prevented feature change coverage detection"
fi

echo 'let value = "same "' >"$REPO/desktop/macos/Desktop/Sources/MainWindow/Pages/LiteralWhitespace.swift"
repo_git add .
repo_git commit -q -m "change user-visible string whitespace"

if coverage_check --root "$REPO" --strict >"$TMPDIR/literal-whitespace.out" 2>"$TMPDIR/literal-whitespace.err"; then
  fail "string-literal whitespace change unexpectedly bypassed strict coverage"
fi
grep -q "UNCOVERED desktop/macos/Desktop/Sources/MainWindow/Pages/LiteralWhitespace.swift" "$TMPDIR/literal-whitespace.out" || \
  fail "string-literal whitespace change was not reported as uncovered"

# SCA-2046: the pinned formatter bootstrap (~20 min from source on a cold
# hosted runner) must happen only when the checked diff actually contains
# desktop Swift sources. Scoped nightly manifest runs invoke this checker with
# only --base when any desktop path is in scope, so an eager resolve billed the
# bootstrap to Swift-free runs.
BOOT_REPO="$TMPDIR/bootstrap-order"
BOOT_LOG="$TMPDIR/bootstrap-order.log"
mkdir -p "$BOOT_REPO/desktop/macos/e2e/flows" "$BOOT_REPO/desktop/macos/Desktop/Sources" \
  "$BOOT_REPO/desktop/macos/scripts" "$BOOT_REPO/backend"
cat >"$BOOT_REPO/desktop/macos/scripts/swift-format-wrapper.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "wrapper:$1" >>"${BOOT_LOG:?BOOT_LOG must be set for the bootstrap-order test}"
if [ "$1" = "binary-path" ]; then
  echo /usr/bin/true
fi
exit 0
SH
chmod +x "$BOOT_REPO/desktop/macos/scripts/swift-format-wrapper.sh"
: >"$BOOT_REPO/desktop/macos/Desktop/.swift-format"
printf 'let value = 1\n' >"$BOOT_REPO/desktop/macos/Desktop/Sources/Alpha.swift"
printf 'baseline\n' >"$BOOT_REPO/backend/README.md"
boot_git() {
  env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE git -C "$BOOT_REPO" "$@"
}
boot_git init -q
boot_git config user.email "desktop-tests@example.com"
boot_git config user.name "Desktop Tests"
boot_git config core.hooksPath /dev/null
boot_git add .
boot_git commit -q -m "baseline"
printf 'docs only\n' >"$BOOT_REPO/backend/README.md"
boot_git add .
boot_git commit -q -m "docs-only change"

if ! BOOT_LOG="$BOOT_LOG" "$SCRIPT" --root "$BOOT_REPO" --base HEAD~1 >"$TMPDIR/no-bootstrap.out" 2>"$TMPDIR/no-bootstrap.err"; then
  cat "$TMPDIR/no-bootstrap.out"
  cat "$TMPDIR/no-bootstrap.err" >&2
  fail "Swift-free diff unexpectedly failed the coverage check"
fi
if [ -s "$BOOT_LOG" ]; then
  cat "$BOOT_LOG" >&2
  fail "a Swift-free diff still invoked the formatter wrapper"
fi

printf 'let value = 2\n' >"$BOOT_REPO/desktop/macos/Desktop/Sources/Alpha.swift"
boot_git add .
boot_git commit -q -m "desktop Swift change"
if ! BOOT_LOG="$BOOT_LOG" "$SCRIPT" --root "$BOOT_REPO" --base HEAD~1 >"$TMPDIR/bootstrap-needed.out" 2>"$TMPDIR/bootstrap-needed.err"; then
  cat "$TMPDIR/bootstrap-needed.out"
  cat "$TMPDIR/bootstrap-needed.err" >&2
  fail "desktop Swift diff unexpectedly failed the coverage check"
fi
grep -q "wrapper:bootstrap" "$BOOT_LOG" || \
  fail "a diff with desktop Swift sources must resolve the pinned formatter"

echo "e2e flow coverage tests passed"
