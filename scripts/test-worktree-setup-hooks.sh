#!/usr/bin/env bash

# Regression for #10352: `make setup` and the installed hooks must not depend on
# `git rev-parse --show-toplevel`, which fails ("this operation must be run in a
# work tree") in some linked-worktree layouts (e.g. a Conductor workspace whose
# gitdir lives under the main clone). When it fails it prints nothing to stdout,
# leaving an empty repo root that produced paths like `/scripts/dev-harness/...`.
#
# Controllable seam: a `git` shim on PATH that makes ONLY `rev-parse
# --show-toplevel` fail (empty stdout, non-zero) and passes everything else
# through to the real git, reproducing the failure on any host/git version.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-worktree-hooks.XXXXXX")"
trap 'rm -rf "$TMPDIR"' EXIT

REAL_GIT="$(command -v git)"
SHIM_DIR="$TMPDIR/shim"
mkdir -p "$SHIM_DIR"
cat >"$SHIM_DIR/git" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "rev-parse" ] && printf '%s\n' "\$@" | grep -q -- '--show-toplevel'; then
  echo "fatal: this operation must be run in a work tree" >&2
  exit 128
fi
exec "$REAL_GIT" "\$@"
EOF
chmod +x "$SHIM_DIR/git"
SHIM_PATH="$SHIM_DIR:$PATH"

fail() { echo "FAIL: $*" >&2; exit 1; }

# --- Test A: install-git-hooks.sh resolves the repo root without --show-toplevel.
REPO="$TMPDIR/repo"
mkdir -p "$REPO/scripts"
git init --initial-branch=main "$REPO" >/dev/null
for f in pre-commit pre-push pre-push-singleflight pr-preflight changed-files; do
  # Record the path the dispatcher execs ($0 == "$ROOT/scripts/<hook>"), so the
  # test can assert the dispatcher resolved ROOT to this worktree.
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$0" > "$PWD/.hook-ran"\n' >"$REPO/scripts/$f"
  chmod +x "$REPO/scripts/$f"
done
cp "$ROOT/scripts/install-git-hooks.sh" "$REPO/scripts/install-git-hooks.sh"
(
  cd "$REPO"
  PATH="$SHIM_PATH" bash scripts/install-git-hooks.sh >/dev/null
)
HOOKS_DIR="$REPO/$("$REAL_GIT" -C "$REPO" rev-parse --git-path hooks)"
[ -x "$HOOKS_DIR/pre-commit" ] || fail "install-git-hooks.sh did not install pre-commit when --show-toplevel fails."
[ -x "$HOOKS_DIR/pre-push" ] || fail "install-git-hooks.sh did not install pre-push when --show-toplevel fails."
grep -q 'ROOT="\$PWD"' "$HOOKS_DIR/pre-commit" || fail "installed dispatcher lacks the PWD fallback for --show-toplevel."

# --- Test C: the installed dispatcher resolves ROOT at runtime via PWD fallback.
(
  cd "$REPO"
  git config user.email t@t.co
  git config user.name t
  echo x > file.txt
  git add -A
  PATH="$SHIM_PATH" git commit -qm trigger
)
[ -f "$REPO/.hook-ran" ] || fail "pre-commit dispatcher did not exec the worktree hook when --show-toplevel fails."
# git runs hooks from the physical worktree root, so ROOT is the canonical path.
REPO_REAL="$(cd "$REPO" && pwd -P)"
[ "$(cat "$REPO/.hook-ran")" = "$REPO_REAL/scripts/pre-commit" ] \
  || fail "dispatcher resolved the wrong repo root: $(cat "$REPO/.hook-ran")"

# --- Test B: the Makefile resolves PYTHON without --show-toplevel.
MREPO="$TMPDIR/mrepo"
mkdir -p "$MREPO/scripts/dev-harness"
git init --initial-branch=main "$MREPO" >/dev/null
cp "$ROOT/scripts/dev-harness/_resolve_python.sh" "$MREPO/scripts/dev-harness/_resolve_python.sh"
cp "$ROOT/Makefile" "$MREPO/Makefile"
printf '\n_print_python:\n\t@echo "PY=$(PYTHON)"\n' >>"$MREPO/Makefile"
OUT="$(cd "$MREPO" && PATH="$SHIM_PATH" make -s _print_python)"
case "$OUT" in
  PY=?*) : ;;
  *) fail "Makefile did not resolve PYTHON when --show-toplevel fails (got: '$OUT')." ;;
esac
printf '%s\n' "$OUT" | grep -q 'dev_harness_python' && fail "Makefile PYTHON resolution broke: $OUT"

echo "worktree setup + hooks regression test passed."
