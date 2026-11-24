#!/usr/bin/env bash
set -euo pipefail

# Git exports GIT_DIR to hooks; from a linked worktree it points at
# .git/worktrees/<name>. When scripts/pre-push passed it on, agents-md-lean's
# self-test ran `git init <fixture>`, which reinitialized the real repository,
# wrote core.bare=true into the config every worktree shares, and failed the
# push of #11183. Four earlier fixes scrubbed the variable one caller at a time
# (#11413, #11709, #11795, #12564); this pins the gate-level scrub that covers
# every child at once.

# Do not pass a caller's repository selection to nested fixture Git commands.
# GIT_NAMESPACE is repository-scoped but absent from Git's local-env-vars list.
GIT_LOCAL_ENV_VARS="$(git rev-parse --local-env-vars)"
for git_env_var in $GIT_LOCAL_ENV_VARS GIT_NAMESPACE; do
  unset "$git_env_var"
done
unset GIT_LOCAL_ENV_VARS git_env_var

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/omi-git-env.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

fixture_git() {
  git -c user.name=fixture -c user.email=fixture@example.com -c init.defaultBranch=main \
    -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"
}

fixture_git init -q "$WORK/main"
fixture_git -C "$WORK/main" commit -q --allow-empty -m init
fixture_git -C "$WORK/main" worktree add -q "$WORK/linked"

mkdir -p "$WORK/linked/scripts/dev-harness"
cp "$ROOT/scripts/pre-push" "$WORK/linked/scripts/pre-push"
# The gate sources this before starting anything else. The stub stands in for
# that first child: it does what the check self-tests do, then ends the run.
cat > "$WORK/linked/scripts/dev-harness/_resolve_python.sh" <<'STUB'
git init -q "$FIXTURE_REPO"
exit 0
STUB

before="$(git config --file "$WORK/main/.git/config" --list)"
(
  cd "$WORK/linked"
  GIT_DIR="$(git rev-parse --absolute-git-dir)" FIXTURE_REPO="$WORK/fixture" \
    bash scripts/pre-push origin "$WORK/unused-remote.git" </dev/null
)
after="$(git config --file "$WORK/main/.git/config" --list)"

if [ "$before" != "$after" ]; then
  echo "FAIL: a child of scripts/pre-push rewrote the config every worktree shares:" >&2
  diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") >&2 || true
  exit 1
fi
if [ ! -d "$WORK/fixture/.git" ]; then
  echo "FAIL: the child's git init went to the hook's GIT_DIR instead of its own fixture" >&2
  exit 1
fi

echo "pre-push git env isolation test passed"
