#!/usr/bin/env bash

# Regression for #10293: `make setup` and the pre-push hook aborted with
# "fatal: this operation must be run in a work tree" inside linked worktrees.
#
# #10401 fixed the Makefile and the installed hook dispatcher, but the scripts
# the dispatcher hands off to (scripts/pre-push, scripts/pre-push-singleflight,
# scripts/pr-preflight) and the Python entrypoints they exec
# (.github/scripts/preflight_runner.py, .github/scripts/pr_preflight.py) still
# resolved the repo root with an unguarded `git rev-parse --show-toplevel`. When
# the invoking git context resolves to a git dir rather than a work tree,
# show-toplevel exits 128 and each of those aborted the gate, forcing a
# --no-verify push that silently bypasses local checks.
#
# A bare GIT_DIR reproduces the exact condition (show-toplevel exits 128) while
# the working directory is a real work tree, so the fallback to it is correct.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-pre-push-wt.XXXXXX")"
trap 'rm -rf "$TMPDIR"' EXIT

BARE="$TMPDIR/bare.git"
git init -q --bare "$BARE"

# Sanity: confirm the reproduction actually triggers the 128 condition, so a
# future git that stops failing here turns this into a visible skip rather than a
# silently vacuous pass.
if GIT_DIR="$BARE" git -C "$ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "SKIP: this git does not surface the show-toplevel work-tree failure; cannot reproduce #10293." >&2
  exit 0
fi

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# A stub python3 that reports the working directory it was exec'd in, so the
# shell resolvers can be exercised against the real script files without running
# the full gate. It shadows python3 only for the exec-style wrappers below.
STUB_BIN="$TMPDIR/bin"
mkdir -p "$STUB_BIN"
cat >"$STUB_BIN/python3" <<'EOF'
#!/usr/bin/env bash
printf 'CWD=%s\n' "$PWD"
EOF
chmod +x "$STUB_BIN/python3"

# scripts/pre-push-singleflight and scripts/pr-preflight both resolve the root,
# cd into it, then exec python3. Under the 128 condition they must reach the
# stub (printing the real work-tree root) instead of aborting at resolution.
for script in pre-push-singleflight pr-preflight; do
  out="$(cd "$ROOT" && GIT_DIR="$BARE" PATH="$STUB_BIN:$PATH" bash "$ROOT/scripts/$script" 2>&1)" \
    || fail "scripts/$script aborted under the work-tree failure: $out"
  case "$out" in
    *"must be run in a work tree"*) fail "scripts/$script still aborts with the work-tree failure: $out" ;;
    "CWD=$ROOT") : ;;
    *) fail "scripts/$script resolved the wrong root under the work-tree failure: $out" ;;
  esac
done

# scripts/pre-push resolves the root, cd's into it, then fails fast on a missing
# base ref (this bare repo has no origin/main). The point is that it gets past
# resolution: the abort must be the base-ref failure, never the work-tree fatal.
out="$(cd "$ROOT" && GIT_DIR="$BARE" bash "$ROOT/scripts/pre-push" origin file://"$BARE" </dev/null 2>&1)" && true
case "$out" in
  *"must be run in a work tree"*) fail "scripts/pre-push still aborts with the work-tree failure: $out" ;;
  *"cannot find"*) : ;;
  *) fail "scripts/pre-push did not reach the base-ref check under the work-tree failure: $out" ;;
esac

# The Python entrypoints resolve the root directly; both must fall back to the
# working directory instead of raising CalledProcessError under the 128 condition.
for probe in \
  "import preflight_runner as m; print(m.resolve_repo_root())" \
  "import pr_preflight as m; print(m._resolve_repo_root())"; do
  out="$(cd "$ROOT" && GIT_DIR="$BARE" python3 -c "import sys; sys.path.insert(0, '$ROOT/.github/scripts'); $probe")" \
    || fail "python resolver aborted under the work-tree failure: $probe"
  [ "$out" = "$ROOT" ] || fail "python resolver returned wrong root ($out) for: $probe"
done

echo "pre-push linked-worktree repo-root fallback test passed."
