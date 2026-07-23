#!/usr/bin/env bash

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

# Git exports repository-local environment variables to hooks. Clear them
# before creating the fixture repository so `git init <path>` cannot re-open
# and mutate the caller's shared repository (especially from a linked worktree).
while IFS= read -r var; do
  unset "$var"
done < <(git rev-parse --local-env-vars)

TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-make-setup.XXXXXX")"
trap 'rm -rf "$TMPDIR"' EXIT

mkdir -p "$TMPDIR/repo/scripts/dev-harness" "$TMPDIR/repo/backend/scripts"
git init --initial-branch=main "$TMPDIR/repo" >/dev/null
cp "$ROOT/Makefile" "$TMPDIR/repo/Makefile"

cat >"$TMPDIR/repo/scripts/dev-harness/_resolve_python.sh" <<'EOF'
dev_harness_python() {
  printf '%s\n' python3
}
EOF

for script in setup-refresh-main.sh install-git-hooks.sh; do
  cat >"$TMPDIR/repo/scripts/$script" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$(basename "$0")" >> setup-order.txt
EOF
  chmod +x "$TMPDIR/repo/scripts/$script"
done

cat >"$TMPDIR/repo/backend/scripts/sync-python-deps.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "backend-sync" >> setup-order.txt
EOF
chmod +x "$TMPDIR/repo/backend/scripts/sync-python-deps.sh"

(
  cd "$TMPDIR/repo"
  make setup >/dev/null
)

expected=$'setup-refresh-main.sh\ninstall-git-hooks.sh\nbackend-sync'
actual="$(cat "$TMPDIR/repo/setup-order.txt")"
if [ "$actual" != "$expected" ]; then
  echo "FAIL: make setup did not provision baseline pre-push prerequisites in order." >&2
  printf 'Expected:\n%s\nActual:\n%s\n' "$expected" "$actual" >&2
  exit 1
fi

echo "make setup baseline prerequisites test passed."

# The baseline target is intentionally safe to rerun: an agent should not have
# to delete a healthy venv just to repeat setup after a branch change.
mkdir -p "$TMPDIR/sync/backend/scripts" "$TMPDIR/sync/bin"
cp "$ROOT/backend/scripts/sync-python-deps.sh" "$TMPDIR/sync/backend/scripts/sync-python-deps.sh"
printf '3.11\n' >"$TMPDIR/sync/backend/.python-version"
# The sync script selects a different checked-in lock by host platform.
# Keep this fixture runnable in macOS, Linux, Windows, and Intel-macOS CI.
touch \
  "$TMPDIR/sync/backend/pylock.toml" \
  "$TMPDIR/sync/backend/pylock.macos.toml" \
  "$TMPDIR/sync/backend/pylock.macos-x86_64.toml" \
  "$TMPDIR/sync/backend/pylock.windows.toml"
cat >"$TMPDIR/sync/bin/uv" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = "python" ]; then
  exit 0
fi
if [ "$1" = "venv" ]; then
  target="${!#}"
  if [ -e "$target" ] && [[ " $* " != *" --allow-existing "* ]]; then
    echo "refusing to replace existing venv" >&2
    exit 42
  fi
  mkdir -p "$target/bin"
  exit 0
fi
if [ "$1" = "pip" ] && [ "$2" = "sync" ]; then
  exit 0
fi
echo "unexpected uv invocation: $*" >&2
exit 1
EOF
chmod +x "$TMPDIR/sync/bin/uv"
(
  cd "$TMPDIR/sync/backend"
  PATH="$TMPDIR/sync/bin:$PATH" bash scripts/sync-python-deps.sh >/dev/null
  PATH="$TMPDIR/sync/bin:$PATH" bash scripts/sync-python-deps.sh >/dev/null
)

echo "backend dependency sync rerun test passed."

# Regression: when `git rev-parse --show-toplevel` cannot resolve a work tree
# (a linked worktree whose git context resolves to a git dir exits 128 here with
# "this operation must be run in a work tree"), the Makefile previously expanded
# the repo root to an empty prefix and broke every target with
# `/scripts/dev-harness/_resolve_python.sh: No such file`. The root now falls
# back to the working directory make runs in, so the resolver must still be found
# and PYTHON must resolve. A bare GIT_DIR reproduces the exact condition:
# show-toplevel exits 128 while `--git-path hooks` still resolves.
FB_ROOT="$TMPDIR/fallback"
mkdir -p "$FB_ROOT/scripts/dev-harness" "$FB_ROOT/backend/.venv/bin"
cp "$ROOT/Makefile" "$FB_ROOT/Makefile"
cat >"$FB_ROOT/scripts/dev-harness/_resolve_python.sh" <<'EOF'
dev_harness_python() {
  local repo_root candidate
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  candidate="$repo_root/backend/.venv/bin/python"
  if [ -x "$candidate" ]; then
    printf '%s\n' "$candidate"
    return
  fi
  printf '%s\n' python3
}
EOF
: >"$FB_ROOT/backend/.venv/bin/python"
chmod +x "$FB_ROOT/backend/.venv/bin/python"
cat >>"$FB_ROOT/Makefile" <<'EOF'

print-resolved-python:
	@printf 'PYTHON=%s\n' "$(PYTHON)"
EOF
git init -q --bare "$TMPDIR/fallback-bare.git"
out="$(cd "$FB_ROOT" && env -u PYTHON GIT_DIR="$TMPDIR/fallback-bare.git" make print-resolved-python 2>/dev/null)"
expected="PYTHON=$(cd "$FB_ROOT" && pwd)/backend/.venv/bin/python"
if [ "$out" != "$expected" ]; then
  echo "FAIL: Makefile repo-root resolution collapsed when show-toplevel could not resolve a work tree." >&2
  printf 'Expected: %s\nGot:      %s\n' "$expected" "$out" >&2
  exit 1
fi
echo "linked-worktree repo-root fallback test passed."
