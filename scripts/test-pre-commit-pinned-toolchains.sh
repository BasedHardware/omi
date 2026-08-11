#!/usr/bin/env bash
set -euo pipefail

# Git hooks export their own repository environment. This fixture creates a
# separate temporary repository, so it must not inherit that hook context.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/scripts/pre-commit"
TMPDIR="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

REPO="$TMPDIR/repo"
STUBS="$TMPDIR/stubs"
mkdir -p "$REPO/web/frontend/src" "$REPO/app/lib" "$REPO/.github/workflows" "$STUBS"
git -C "$REPO" init -q
git -C "$REPO" config user.email test@example.com
git -C "$REPO" config user.name test
printf 'jobs:\n  flutter:\n    steps:\n      - uses: subosito/flutter-action@v2\n        with:\n          flutter-version: 9.9.9\n' >"$REPO/.github/workflows/repo-checks.yml"
printf '{\n  "devDependencies": {\n    "eslint-plugin-prettier": "^4.2.1",\n    "prettier": "^2.8.8"\n  }\n}\n' >"$REPO/web/frontend/package.json"
printf 'const a = 0\n' >"$REPO/web/frontend/src/a.ts"
printf 'void main() {}\n' >"$REPO/app/lib/main.dart"
git -C "$REPO" add -A
git -C "$REPO" commit -qm base

make_prettier_stub() {
  version="$1"
  mkdir -p "$REPO/web/frontend/node_modules/.bin"
  cat >"$REPO/web/frontend/node_modules/.bin/prettier" <<STUB
#!/bin/sh
if [ "\$1" = "--version" ]; then echo "$version"; exit 0; fi
shift
for f in "\$@"; do printf 'PRETTIER_${version}_FORMATTED\n' >"\$f"; done
STUB
  chmod +x "$REPO/web/frontend/node_modules/.bin/prettier"
}

make_flutter_stub() {
  cat >"$STUBS/flutter" <<STUB
#!/bin/sh
echo "Flutter $1 • channel stable"
STUB
  cat >"$STUBS/dart" <<'STUB'
#!/bin/sh
for f in "$@"; do
  case "$f" in
    *.dart) printf 'DART_FORMATTED\n' >"$f" ;;
  esac
done
STUB
  chmod +x "$STUBS/flutter" "$STUBS/dart"
}

run_hook() {
  ( cd "$REPO" && env PATH="$STUBS:$PATH" "$@" sh "$HOOK" )
}

expect_refusal() {
  label="$1"
  shift
  out="$TMPDIR/out.txt"
  if run_hook "$@" >"$out" 2>&1; then
    echo "FAIL: $label — hook exited 0 instead of refusing" >&2
    cat "$out" >&2
    exit 1
  fi
  if ! grep -q "mismatch\|refusing" "$out"; then
    echo "FAIL: $label — refusal message is not actionable" >&2
    cat "$out" >&2
    exit 1
  fi
}

# --- Prettier: no pinned toolchain installed must refuse, not reformat ---
printf 'const a = {b:1}\n' >"$REPO/web/frontend/src/a.ts"
git -C "$REPO" add web/frontend/src/a.ts
rm -rf "$REPO/web/frontend/node_modules"
expect_refusal "missing pinned prettier"
test "$(cat "$REPO/web/frontend/src/a.ts")" = "const a = {b:1}"

# --- Prettier: a mismatched major (the floating npx hazard) must refuse ---
make_prettier_stub 3.4.2
expect_refusal "prettier major mismatch"
test "$(cat "$REPO/web/frontend/src/a.ts")" = "const a = {b:1}"

# --- Prettier: the pinned major formats ---
make_prettier_stub 2.8.8
run_hook >/dev/null
grep -q 'PRETTIER_2.8.8_FORMATTED' "$REPO/web/frontend/src/a.ts"
git -C "$REPO" reset -q --hard

# --- Dart: no flutter on PATH must refuse ---
printf 'void main() {  }\n' >"$REPO/app/lib/main.dart"
git -C "$REPO" add app/lib/main.dart
expect_refusal "no flutter toolchain"
test "$(cat "$REPO/app/lib/main.dart")" = "void main() {  }"

# --- Dart: a Flutter version other than the repo pin must refuse ---
make_flutter_stub 8.8.8
expect_refusal "flutter version mismatch"
test "$(cat "$REPO/app/lib/main.dart")" = "void main() {  }"

# --- Dart: the pinned Flutter formats ---
make_flutter_stub 9.9.9
run_hook >/dev/null
grep -q 'DART_FORMATTED' "$REPO/app/lib/main.dart"

# --- Both hatches leave staged files untouched and still commit ---
git -C "$REPO" reset -q --hard
printf 'const c = {d:1}\n' >"$REPO/web/frontend/src/a.ts"
printf 'void main() {   }\n' >"$REPO/app/lib/main.dart"
git -C "$REPO" add -A
rm -rf "$REPO/web/frontend/node_modules" "$STUBS/flutter"
run_hook OMI_SKIP_WEB_FORMAT=1 OMI_SKIP_DART_FORMAT=1 >/dev/null
test "$(cat "$REPO/web/frontend/src/a.ts")" = "const c = {d:1}"
test "$(cat "$REPO/app/lib/main.dart")" = "void main() {   }"

echo "pre-commit pinned-toolchain refusal tests passed"
