#!/usr/bin/env bash

set -euo pipefail

# Git invokes hooks with GIT_DIR pointed at the worktree's private git
# directory. Resolve this test's source root from its own path rather than
# asking Git for a work tree, which is precisely the linked-worktree condition
# the final fixture below verifies.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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

# The automatic linked-worktree bootstrap must use the same canonical setup
# target. This is a static configuration check: it prevents the worktree
# launcher from silently falling back to ambient pip installs that do not
# install the shared Git hook dispatcher or the locked backend environment.
python3 - "$ROOT/.cursor/worktrees.json" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
config = json.loads(config_path.read_text(encoding="utf-8"))
for name in ("setup-worktree", "setup-worktree-unix", "setup-worktree-windows"):
    commands = config.get(name)
    if not isinstance(commands, list) or not any(command.strip() == "make setup" for command in commands):
        raise SystemExit(f"FAIL: {name} must invoke the canonical 'make setup' target")
    if any("pip install -r requirements.txt" in command for command in commands):
        raise SystemExit(f"FAIL: {name} still uses an ambient requirements.txt install")
print("automatic worktree bootstrap uses canonical make setup")
PY

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
# Git for Windows derives extensionless-file executability from a shebang;
# chmod alone leaves an empty fixture non-executable on NTFS.
cat >"$FB_ROOT/backend/.venv/bin/python" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$FB_ROOT/backend/.venv/bin/python"
cat >>"$FB_ROOT/Makefile" <<'EOF'

print-resolved-python:
	@printf 'PYTHON=%s\n' "$(PYTHON)"
EOF
git init -q --bare "$TMPDIR/fallback-bare.git"
# This contract also runs beneath `make preflight`; suppress nested Make's
# directory banner so stdout remains the resolver value under both entrypoints.
out="$(cd "$FB_ROOT" && env -u PYTHON GIT_DIR="$TMPDIR/fallback-bare.git" make --no-print-directory print-resolved-python 2>/dev/null)"
# Both sides are compared as physical paths, because each platform hands back a different
# *name* for the same directory: Git Bash exposes /tmp as a logical mount while BASH_SOURCE
# resolves it through a Windows path, and macOS puts TMPDIR under /var, a symlink to
# /private/var. Canonicalising only the expectation is what made this fail on every machine
# where the resolver answered with the short name — the two strings named one file, and a
# string compare cannot tell.
expected="PYTHON=$(cd "$FB_ROOT" && pwd -P)/backend/.venv/bin/python"
actual_path="${out#PYTHON=}"
actual_dir="$(cd "$(dirname "$actual_path")" 2>/dev/null && pwd -P || true)"
actual="PYTHON=${actual_dir:-$(dirname "$actual_path")}/$(basename "$actual_path")"
if [ "$actual" != "$expected" ]; then
  echo "FAIL: Makefile repo-root resolution collapsed when show-toplevel could not resolve a work tree." >&2
  printf 'Expected: %s\nGot:      %s (raw: %s)\n' "$expected" "$actual" "$out" >&2
  exit 1
fi
echo "linked-worktree repo-root fallback test passed."

# Regression: mistaken core.bare=true on a primary checkout (directory .git) breaks
# git status and worktree spawning from the main path.
MISBARE_ROOT="$TMPDIR/misbare"
git init -q --initial-branch=main "$MISBARE_ROOT"
git -C "$MISBARE_ROOT" config core.bare true
if [ "$(git -C "$MISBARE_ROOT" rev-parse --is-inside-work-tree)" = "true" ]; then
  echo "FAIL: misbare fixture should not report inside-work-tree before repair." >&2
  exit 1
fi
bash "$ROOT/scripts/repair-git-primary-worktree.sh" "$MISBARE_ROOT"
if [ "$(git -C "$MISBARE_ROOT" config --get core.bare)" != "false" ]; then
  echo "FAIL: repair-git-primary-worktree.sh did not clear core.bare." >&2
  exit 1
fi
if [ "$(git -C "$MISBARE_ROOT" rev-parse --is-inside-work-tree)" != "true" ]; then
  echo "FAIL: primary checkout still not a work tree after core.bare repair." >&2
  exit 1
fi
echo "repair-git-primary-worktree test passed."

# Regression: git accepts many true spellings (yes, on, 1, TRUE …). The repair
# must canonicalise via --bool, not compare the raw value to "true".
for spelling in yes on 1 TRUE; do
  git -C "$MISBARE_ROOT" config core.bare "$spelling"
  if [ "$(git -C "$MISBARE_ROOT" rev-parse --is-inside-work-tree)" = "true" ]; then
    echo "FAIL: misbare fixture should not report inside-work-tree for spelling '$spelling'." >&2
    exit 1
  fi
  bash "$ROOT/scripts/repair-git-primary-worktree.sh" "$MISBARE_ROOT"
  if [ "$(git -C "$MISBARE_ROOT" config --get core.bare)" != "false" ]; then
    echo "FAIL: repair did not clear core.bare spelling '$spelling'." >&2
    exit 1
  fi
done
echo "repair-git-primary-worktree boolean-spelling test passed."
