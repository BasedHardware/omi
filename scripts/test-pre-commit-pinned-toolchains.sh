#!/usr/bin/env bash
set -euo pipefail

# Git hooks export their own repository environment. This fixture creates a
# separate temporary repository, so it must not inherit that hook context.
# Do not pass a caller's repository selection to nested fixture Git commands.
# GIT_NAMESPACE is repository-scoped but absent from Git's local-env-vars list.
GIT_LOCAL_ENV_VARS="$(git rev-parse --local-env-vars)"
for git_env_var in $GIT_LOCAL_ENV_VARS GIT_NAMESPACE; do
  unset "$git_env_var"
done
unset GIT_LOCAL_ENV_VARS git_env_var

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/scripts/pre-commit"
BACKEND_FORMATTER="$ROOT/scripts/backend-python-format"
TMPDIR="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

REPO="$TMPDIR/repo"
STUBS="$TMPDIR/stubs"
mkdir -p "$REPO/web/frontend/src" "$REPO/app/lib" "$REPO/.github/workflows" "$REPO/.github/scripts" "$REPO/scripts" "$STUBS"
cp "$BACKEND_FORMATTER" "$REPO/scripts/backend-python-format"
git -C "$REPO" init -q
git -C "$REPO" config user.email test@example.com
git -C "$REPO" config user.name test
# The hook gates the fixture repo's commit identity; the author check is not
# what this lane covers, so stub it to always pass.
cat >"$REPO/.github/scripts/check_git_author_identity.py" <<'PY'
#!/usr/bin/env python3
import sys
sys.exit(0)
PY
printf 'jobs:\n  flutter:\n    steps:\n      - uses: subosito/flutter-action@v2\n        with:\n          flutter-version: 9.9.9\n' >"$REPO/.github/workflows/repo-checks.yml"
printf '{\n  "devDependencies": {\n    "eslint-plugin-prettier": "^4.2.1",\n    "prettier": "^2.8.8",\n    "prettier-plugin-tailwindcss": "^0.3.0"\n  }\n}\n' >"$REPO/web/frontend/package.json"
cat >"$REPO/web/frontend/package-lock.json" <<LOCK
{
  "name": "fixture",
  "version": "0.0.0",
  "lockfileVersion": 3,
  "packages": {
    "": {
      "name": "fixture",
      "version": "0.0.0"
    },
    "node_modules/prettier": {
      "version": "2.8.8"
    },
    "node_modules/prettier-plugin-tailwindcss": {
      "version": "0.3.0"
    }
  }
}
LOCK
printf 'const a = 0\n' >"$REPO/web/frontend/src/a.ts"
printf 'void main() {}\n' >"$REPO/app/lib/main.dart"
mkdir -p "$REPO/app/.dart_tool"
printf '{"configVersion": 2, "packages": []}\n' >"$REPO/app/.dart_tool/package_config.json"
git -C "$REPO" add -A
git -C "$REPO" commit -qm base

make_prettier_stub() {
  target_dir="$1"
  version="$2"
  mkdir -p "$target_dir/node_modules/.bin"
  cat >"$target_dir/node_modules/.bin/prettier" <<STUB
#!/bin/sh
if [ "\$1" = "--version" ]; then echo "$version"; exit 0; fi
shift
for f in "\$@"; do printf 'PRETTIER_${version}_FORMATTED\n' >"\$f"; done
STUB
  chmod +x "$target_dir/node_modules/.bin/prettier"
}

make_prettier_lock() {
  target_dir="$1"
  version="$2"
  cat >"$target_dir/package-lock.json" <<LOCK
{
  "name": "fixture",
  "version": "0.0.0",
  "lockfileVersion": 3,
  "packages": {
    "": {
      "name": "fixture",
      "version": "0.0.0"
    },
    "node_modules/prettier": {
      "version": "$version"
    },
    "node_modules/prettier-plugin-tailwindcss": {
      "version": "0.3.0"
    }
  }
}

LOCK
}

make_bun_lock() {
  target_dir="$1"
  version="$2"
  cat >"$target_dir/bun.lock" <<LOCK
{
  "lockfileVersion": 1,
  "workspaces": {
    "": {
      "devDependencies": {
        "prettier": "^$version",
        "prettier-plugin-tailwindcss": "^0.3.0",
      },
    },
  },
  "packages": {
    "prettier": ["prettier@$version", "", {}, "sha512-fixture"],
    "prettier-plugin-tailwindcss": ["prettier-plugin-tailwindcss@0.3.0", "", {}, "sha512-fixture"],
  },
}
LOCK
}

make_prettier_plugin() {
  target_dir="$1"
  version="${2:-0.3.0}"
  mkdir -p "$target_dir/node_modules/prettier-plugin-tailwindcss"
  printf '{"name": "prettier-plugin-tailwindcss", "version": "%s"}\n' "$version" >"$target_dir/node_modules/prettier-plugin-tailwindcss/package.json"
}

make_flutter_stub() {
  cat >"$STUBS/flutter" <<STUB
#!/bin/sh
# Mimic Flutter's Git-based SDK-version resolution: a leaked hook GIT_DIR (as in
# a linked worktree) makes the probe report nothing even for a valid install.
if [ -n "\${GIT_DIR:-}" ]; then exit 0; fi
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

make_clang_format_stub() {
  cat >"$STUBS/clang-format" <<STUB
#!/bin/sh
if [ "\$1" = "--version" ]; then
  echo "$1"
  exit 0
fi
for arg in "\$@"; do
  case "\$arg" in
    *.c|*.cpp|*.cc|*.cxx|*.h|*.hpp) printf 'CLANG_FORMATTED\n' >"\$arg" ;;
  esac
done
STUB
  chmod +x "$STUBS/clang-format"
}

# PATH without the host's clang-format, so the missing-formatter case stays
# deterministic even where a real clang-format is installed (stubs shadow it
# elsewhere; here nothing may fall through to the host toolchain). Resolve
# tools outside PATH-manager wrappers: the managed git shim needs realpath and
# dirname on PATH, so prefer the system toolchain like CI's runner has.
minimal_tool() {
  for candidate in "/usr/bin/$1" "/bin/$1" "$(command -v "$1" 2>/dev/null)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  echo "cannot resolve $1 for the minimal PATH fixture" >&2
  exit 1
}
MINIMAL_BIN="$TMPDIR/minimal-bin"
mkdir -p "$MINIMAL_BIN"
for hook_tool in sh git python3 sed grep head xargs cat; do
  ln -s "$(minimal_tool "$hook_tool")" "$MINIMAL_BIN/$hook_tool"
done

make_black_stub() {
  cat >"$STUBS/black" <<'STUB'
#!/bin/sh
if [ "${1:-}" = "--version" ]; then
  echo "black, 26.5.1 (compiled: yes)"
  exit 0
fi
for arg in "$@"; do
  case "$arg" in
    *.py) printf 'PYTHON_FORMATTED\n' >"$arg" ;;
  esac
done
STUB
  chmod +x "$STUBS/black"
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
  if ! grep -q "mismatch\|refus\|unresolved" "$out"; then
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

# --- Prettier: a mismatched version (the floating npx hazard) must refuse ---
make_prettier_stub "$REPO/web/frontend" 3.4.2
expect_refusal "prettier version mismatch"
test "$(cat "$REPO/web/frontend/src/a.ts")" = "const a = {b:1}"

# --- Prettier: an older same-major release must still be refused when package-lock pins newer ---
make_prettier_stub "$REPO/web/frontend" 2.0.0
expect_refusal "prettier same-major stale lock"
test "$(cat "$REPO/web/frontend/src/a.ts")" = "const a = {b:1}"

# --- Prettier: the pinned version formats ---
make_prettier_stub "$REPO/web/frontend" 2.8.8
make_prettier_plugin "$REPO/web/frontend" 0.3.0
run_hook >/dev/null
grep -q 'PRETTIER_2.8.8_FORMATTED' "$REPO/web/frontend/src/a.ts"
git -C "$REPO" reset -q --hard

# --- Prettier: a stale plugin must still be refused when prettier matches ---
printf 'const a = {b:1}\n' >"$REPO/web/frontend/src/a.ts"
git -C "$REPO" add web/frontend/src/a.ts
make_prettier_stub "$REPO/web/frontend" 2.8.8
make_prettier_plugin "$REPO/web/frontend" 0.2.0
expect_refusal "prettier plugin version mismatch"
test "$(cat "$REPO/web/frontend/src/a.ts")" = "const a = {b:1}"
git -C "$REPO" reset -q --hard

# --- Prettier: a declared plugin missing from the lockfile must refuse, not skip ---
printf 'const a = {b:1}\n' >"$REPO/web/frontend/src/a.ts"
git -C "$REPO" add web/frontend/src/a.ts
cat >"$REPO/web/frontend/package-lock.json" <<LOCK
{
  "name": "fixture",
  "version": "0.0.0",
  "lockfileVersion": 3,
  "packages": {
    "": {
      "name": "fixture",
      "version": "0.0.0"
    },
    "node_modules/prettier": {
      "version": "2.8.8"
    }
  }
}
LOCK
git -C "$REPO" add web/frontend/package-lock.json
make_prettier_stub "$REPO/web/frontend" 2.8.8
make_prettier_plugin "$REPO/web/frontend" 0.2.0
expect_refusal "declared prettier plugin unresolved in lockfile"
test "$(cat "$REPO/web/frontend/src/a.ts")" = "const a = {b:1}"
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

# --- Dart: a linked-worktree GIT_DIR must not leak into the flutter probe ---
printf 'void main() {  }\n' >"$REPO/app/lib/main.dart"
git -C "$REPO" add app/lib/main.dart
run_hook GIT_DIR="$REPO/.git" >/dev/null
grep -q 'DART_FORMATTED' "$REPO/app/lib/main.dart"

# --- Dart: without package_config.json the SDK ignores the package language
# version and rewrites whole files, so the hook must refuse ---
mv "$REPO/app/.dart_tool/package_config.json" "$TMPDIR/package_config.json"
printf 'void main() {  }\n' >"$REPO/app/lib/main.dart"
git -C "$REPO" add app/lib/main.dart
expect_refusal "missing app package_config.json"
test "$(cat "$REPO/app/lib/main.dart")" = "void main() {  }"
mv "$TMPDIR/package_config.json" "$REPO/app/.dart_tool/package_config.json"

# --- Merge commit: files staged exactly as the incoming side has them are left
# alone (no reformat, no toolchain refusal); a resolved file is still formatted ---
git -C "$REPO" reset -q --hard
git -C "$REPO" checkout -q -b incoming
printf 'void incoming() {  }\n' >"$REPO/app/lib/incoming.dart"
printf 'void resolved() {  }\n' >"$REPO/app/lib/resolved.dart"
printf 'const incoming = {x:1}\n' >"$REPO/web/frontend/src/incoming.ts"
git -C "$REPO" add -A
git -C "$REPO" commit -qm incoming
git -C "$REPO" checkout -q -
printf 'void branch() {}\n' >"$REPO/app/lib/branch.dart"
git -C "$REPO" add -A
git -C "$REPO" commit -qm branch
git -C "$REPO" merge -q --no-commit --no-ff incoming >/dev/null 2>&1
printf 'void resolved() {   }\n' >"$REPO/app/lib/resolved.dart"
git -C "$REPO" add app/lib/resolved.dart
rm -rf "$REPO/web/frontend/node_modules"
run_hook >/dev/null
test "$(cat "$REPO/app/lib/incoming.dart")" = "void incoming() {  }"
test "$(cat "$REPO/web/frontend/src/incoming.ts")" = "const incoming = {x:1}"
grep -q 'DART_FORMATTED' "$REPO/app/lib/resolved.dart"
git -C "$REPO" merge --abort
git -C "$REPO" branch -q -D incoming

# --- Both hatches leave staged files untouched and still commit ---
git -C "$REPO" reset -q --hard
printf 'const c = {d:1}\n' >"$REPO/web/frontend/src/a.ts"
printf 'void main() {   }\n' >"$REPO/app/lib/main.dart"
git -C "$REPO" add -A
rm -rf "$REPO/web/frontend/node_modules" "$STUBS/flutter"
run_hook OMI_SKIP_WEB_FORMAT=1 OMI_SKIP_DART_FORMAT=1 >/dev/null
test "$(cat "$REPO/web/frontend/src/a.ts")" = "const c = {d:1}"
test "$(cat "$REPO/app/lib/main.dart")" = "void main() {   }"

git -C "$REPO" reset -q --hard

# --- Web/app and web/admin now pin prettier, so they format like web/frontend ---
for webdir in web/app web/admin; do
  mkdir -p "$REPO/$webdir/src"
  printf '{\n  "devDependencies": {\n    "prettier": "^2.8.8",\n    "prettier-plugin-tailwindcss": "^0.3.0"\n  }\n}\n' >"$REPO/$webdir/package.json"
  if [ "$webdir" = "web/app" ]; then
    make_bun_lock "$REPO/$webdir" 2.8.8
  else
    make_prettier_lock "$REPO/$webdir" 2.8.8
  fi
  make_prettier_stub "$REPO/$webdir" 2.8.8
  make_prettier_plugin "$REPO/$webdir" 0.3.0
  printf 'const %s = {b:1}\n' "$(basename "$webdir")" >"$REPO/$webdir/src/a.ts"
  git -C "$REPO" add -A
  if [ "$webdir" = "web/app" ]; then
    make_prettier_stub "$REPO/$webdir" 2.0.0
    expect_refusal "bun lock prettier version mismatch"
    test "$(cat "$REPO/$webdir/src/a.ts")" = "const app = {b:1}"
    make_prettier_stub "$REPO/$webdir" 2.8.8
  fi
  run_hook >/dev/null
  grep -q 'PRETTIER_2.8.8_FORMATTED' "$REPO/$webdir/src/a.ts"
  git -C "$REPO" reset -q --hard
  rm -rf "$REPO/$webdir"
done

# --- A web directory without a prettier pin is still refused ---
mkdir -p "$REPO/web/unpinned/src"
printf '{ "devDependencies": {} }\n' >"$REPO/web/unpinned/package.json"
printf 'const x = {b:1}\n' >"$REPO/web/unpinned/src/a.ts"
git -C "$REPO" add -A
expect_refusal "unpinned web dir"
test "$(cat "$REPO/web/unpinned/src/a.ts")" = "const x = {b:1}"

# --- A staged web file with unstaged edits is refused instead of sweeping them in ---
mkdir -p "$REPO/web/admin/src"
printf '{\n  "devDependencies": {\n    "prettier": "^2.8.8",\n    "prettier-plugin-tailwindcss": "^0.3.0"\n  }\n}\n' >"$REPO/web/admin/package.json"
make_prettier_lock "$REPO/web/admin" 2.8.8
make_prettier_stub "$REPO/web/admin" 2.8.8
make_prettier_plugin "$REPO/web/admin" 0.3.0
git -C "$REPO" add web/admin/package.json web/admin/package-lock.json
printf 'const staged = {b:1}\n' >"$REPO/web/admin/src/a.ts"
git -C "$REPO" add web/admin/src/a.ts
printf 'const staged = {b:1}\nconst unstaged = 2\n' >"$REPO/web/admin/src/a.ts"
expect_refusal "web file with unstaged edits"
test "$(cat "$REPO/web/admin/src/a.ts")" = "const staged = {b:1}
const unstaged = 2"
git -C "$REPO" add web/admin/src/a.ts
rm -rf "$REPO/web/unpinned"
git -C "$REPO" reset -q -- web/unpinned
run_hook >/dev/null
grep -q 'PRETTIER_2.8.8_FORMATTED' "$REPO/web/admin/src/a.ts"

# --- The generated OpenAPI client under web/admin is excluded from format-and-add ---
mkdir -p "$REPO/web/admin/lib/services/omi-api"
printf 'export const omiApi = {  untouched: 1 }\n' >"$REPO/web/admin/lib/services/omi-api/omiApi.generated.ts"
printf 'const gen = {b:1}\n' >"$REPO/web/admin/src/b.ts"
git -C "$REPO" add web/admin/lib/services/omi-api/omiApi.generated.ts web/admin/src/b.ts
run_hook >/dev/null
grep -q 'PRETTIER_2.8.8_FORMATTED' "$REPO/web/admin/src/b.ts"
test "$(cat "$REPO/web/admin/lib/services/omi-api/omiApi.generated.ts")" = "export const omiApi = {  untouched: 1 }"
git -C "$REPO" reset -q --hard

# --- A missing package-lock with a matching-major prettier must refuse, not fall back (#11304) ---
mkdir -p "$REPO/web/nolock/src"
printf '{\n  "devDependencies": {\n    "prettier": "^2.8.8",\n    "prettier-plugin-tailwindcss": "^0.3.0"\n  }\n}\n' >"$REPO/web/nolock/package.json"
make_prettier_stub "$REPO/web/nolock" 2.0.0
make_prettier_plugin "$REPO/web/nolock" 0.3.0
printf 'const nolock = {b:1}\n' >"$REPO/web/nolock/src/a.ts"
git -C "$REPO" add web/nolock/src/a.ts web/nolock/package.json
expect_refusal "missing lockfile with same-major prettier"
test "$(cat "$REPO/web/nolock/src/a.ts")" = "const nolock = {b:1}"

# --- Backend Python uses the shared pinned formatter and re-stages its output ---
git -C "$REPO" reset -q --hard
mkdir -p "$REPO/backend"
printf 'x=  1\n' >"$REPO/backend/example.py"
git -C "$REPO" add backend/example.py
make_black_stub
run_hook >/dev/null
test "$(cat "$REPO/backend/example.py")" = "PYTHON_FORMATTED"
git -C "$REPO" diff --exit-code -- backend/example.py >/dev/null
git -C "$REPO" diff --cached -- backend/example.py | grep -q 'PYTHON_FORMATTED'

# --- Firmware C: CI's Formatting check uses clang-format 18, so a missing
# formatter or any other major must refuse and leave the staged bytes
# untouched; 18 formats and re-stages (the safe_mode.c churn hazard) ---
git -C "$REPO" reset -q --hard
mkdir -p "$REPO/omi/firmware/omi/src"
printf 'void boot(void) { fail = (struct boot_info){0}; }\n' >"$REPO/omi/firmware/omi/src/safe_mode.c"
git -C "$REPO" add omi/firmware/omi/src/safe_mode.c
rm -f "$STUBS/clang-format"
expect_refusal "no clang-format on PATH" PATH="$MINIMAL_BIN"
test "$(cat "$REPO/omi/firmware/omi/src/safe_mode.c")" = "void boot(void) { fail = (struct boot_info){0}; }"
make_clang_format_stub "Homebrew clang-format version 23.1.1"
expect_refusal "clang-format major mismatch"
test "$(cat "$REPO/omi/firmware/omi/src/safe_mode.c")" = "void boot(void) { fail = (struct boot_info){0}; }"
make_clang_format_stub "clang-format version 18.1.8"
run_hook >/dev/null
grep -q 'CLANG_FORMATTED' "$REPO/omi/firmware/omi/src/safe_mode.c"
git -C "$REPO" diff --cached -- omi/firmware/omi/src/safe_mode.c | grep -q 'CLANG_FORMATTED'
git -C "$REPO" reset -q --hard
rm -f "$STUBS/clang-format"

echo "pre-commit pinned-toolchain refusal tests passed"
