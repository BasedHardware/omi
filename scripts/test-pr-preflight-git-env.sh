#!/usr/bin/env bash
set -euo pipefail

# 2026-11-04 00:10Z: pr-preflight passed a lane's GIT_DIR/GIT_WORK_TREE
# to a nested git init, which wrote core.worktree into the shared config.
GIT_LOCAL_ENV_VARS="$(git rev-parse --local-env-vars)"
for git_env_var in $GIT_LOCAL_ENV_VARS GIT_NAMESPACE; do
  unset "$git_env_var"
done
unset GIT_LOCAL_ENV_VARS git_env_var

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/omi-git-env.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

fixture_git() {
  git -c user.name=fixture -c user.email=fixture@example.com -c init.defaultBranch=main \
    -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"
}
fixture_git init -q "$WORK/main"
fixture_git -C "$WORK/main" commit -q --allow-empty -m init
fixture_git -C "$WORK/main" worktree add -q "$WORK/linked"
GITDIR="$(git -C "$WORK/linked" rev-parse --absolute-git-dir)"
COMMON="$(git -C "$WORK/main" rev-parse --absolute-git-dir)"
mkdir -p "$WORK/linked/scripts/dev-harness" "$WORK/linked/.github/scripts"
cp "$ROOT/scripts/pr-preflight" "$WORK/linked/scripts/pr-preflight"
# Use the repository's normal resolver to select a supported real interpreter.
source "$ROOT/scripts/dev-harness/_resolve_python.sh"
TEST_PYTHON="$(dev_harness_python)"
export TEST_PYTHON

# Scrubbing must precede the sourced resolver as well as both Python runners.
cat > "$WORK/linked/scripts/dev-harness/_resolve_python.sh" <<'STUB'
git init -q "$FIXTURE_REPO/resolver"
dev_harness_python() { printf '%s\n' "$TEST_PYTHON"; }
dev_harness_python_floor_ok() { return 0; }
STUB
cat > "$WORK/linked/.github/scripts/pr_preflight.py" <<'STUB'
import os
from pathlib import Path
import subprocess

assert Path.cwd().resolve() == Path(os.environ['EXPECTED_ROOT']).resolve()
local_vars = subprocess.check_output(['git', 'rev-parse', '--local-env-vars'], text=True).split()
assert not set([*local_vars, 'GIT_NAMESPACE']).intersection(os.environ)
subprocess.run(['git', 'init', '-q', os.environ['FIXTURE_REPO'] + '/check'], check=True)
Path(os.environ['FIXTURE_REPO'], 'runner').write_text(Path(__file__).name)
STUB
cp "$WORK/linked/.github/scripts/pr_preflight.py" "$WORK/linked/scripts/pr_preflight_all.py"
cp "$COMMON/config" "$WORK/config.before"

# Invoke from outside the selected tree: root resolution must still honor the
# incoming environment, then ordinary Git discovery must work after the scrub.
for mode in default all env-all hook-all; do
  args=()
  expected=pr_preflight.py
  all_flag=0
  hook_flag=0
  case "$mode" in
    all) args=(--all); expected=pr_preflight_all.py ;;
    env-all) all_flag=1; expected=pr_preflight_all.py ;;
    hook-all) hook_flag=1; expected=pr_preflight_all.py ;;
  esac
  (
    cd "$WORK/main"
    GIT_DIR="$GITDIR" GIT_WORK_TREE="$WORK/linked" GIT_COMMON_DIR="$COMMON" \
      GIT_INDEX_FILE="$GITDIR/index" GIT_OBJECT_DIRECTORY="$COMMON/objects" \
      GIT_ALTERNATE_OBJECT_DIRECTORIES="$COMMON/objects" GIT_NAMESPACE=fixture GIT_PREFIX=caller/ \
      EXPECTED_ROOT="$WORK/linked" FIXTURE_REPO="$WORK/$mode" \
      OMI_PREFLIGHT_ALL="$all_flag" PRE_PUSH_PREFLIGHT_ALL="$hook_flag" \
      bash "$WORK/linked/scripts/pr-preflight" "${args[@]+"${args[@]}"}"
  )
  cmp "$WORK/config.before" "$COMMON/config"
  if git config --file "$COMMON/config" --get core.worktree; then
    echo "FAIL: nested git init wrote core.worktree into the common config" >&2
    exit 1
  fi
  test -d "$WORK/$mode/resolver/.git"
  test -d "$WORK/$mode/check/.git"
  test "$(cat "$WORK/$mode/runner")" = "$expected"
done

echo "pr-preflight git env isolation test passed"
