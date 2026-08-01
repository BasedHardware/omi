#!/usr/bin/env bash

set -euo pipefail

# Resolve the repo root from this script's own location, not `git rev-parse
# --show-toplevel`. In a linked worktree whose git context resolves to a git dir
# rather than a work tree, show-toplevel exits 128 ("this operation must be run
# in a work tree") and setup-hooks dies with Error 128. `--git-path hooks` works
# in that context (it does not require a work tree), so keep it for HOOKS_DIR.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$(git rev-parse --git-path hooks)"

mkdir -p "$HOOKS_DIR"

# Linked worktrees share the hook directory, so do not symlink hooks to this
# checkout. Dispatch at runtime to the worktree that invoked Git.
install_dispatch_hook() {
  local hook_name="$1"
  local hook_path="$HOOKS_DIR/$hook_name"

  rm -f "$hook_path"
  cat >"$hook_path" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

# Git runs hooks with the working directory at the top of the invoking work
# tree, so fall back to it when show-toplevel cannot resolve a work tree (linked
# worktree git-dir contexts exit 128 here and otherwise abort the hook, forcing
# a --no-verify push that silently bypasses the local gate).
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
HOOK_NAME="$(basename "$0")"

# Hooks run with the maintainer's privileges against whatever branch is checked
# out, so checking out a contributor PR branch would otherwise execute their
# edits to scripts/ on the next commit or push. Only dispatch to a script whose
# content is byte-identical to the same path at a trusted ref.
TRUSTED_REF="${OMI_TRUSTED_HOOK_REF:-origin/main}"
TRUSTED_REF_AVAILABLE=1
if [ "${OMI_ALLOW_UNTRUSTED_HOOKS:-0}" != "1" ] &&
  ! git -C "$ROOT" rev-parse --quiet --verify "$TRUSTED_REF^{commit}" >/dev/null 2>&1; then
  TRUSTED_REF_AVAILABLE=0
  echo "omi hooks: warning: $TRUSTED_REF is not available locally; running $HOOK_NAME unverified." >&2
  echo "omi hooks: run 'git fetch origin main' to re-enable hook verification." >&2
fi

assert_trusted_hook_script() {
  local rel="$1"
  local trusted_blob local_blob
  if [ "${OMI_ALLOW_UNTRUSTED_HOOKS:-0}" = "1" ] || [ "$TRUSTED_REF_AVAILABLE" != "1" ]; then
    return 0
  fi

  if trusted_blob="$(git -C "$ROOT" rev-parse --quiet --verify "$TRUSTED_REF:$rel" 2>/dev/null)" &&
    local_blob="$(git -C "$ROOT" hash-object -- "$ROOT/$rel" 2>/dev/null)" &&
    [ -n "$trusted_blob" ] && [ "$trusted_blob" = "$local_blob" ]; then
    return 0
  fi

  echo "omi hooks: refusing to run $rel — it does not match $TRUSTED_REF." >&2
  echo "omi hooks: the checked-out branch modifies (or removes) a hook script, which would" >&2
  echo "omi hooks: execute that branch's code on your machine. Review the diff:" >&2
  echo "omi hooks:   git diff $TRUSTED_REF -- $rel" >&2
  echo "omi hooks: to run it anyway, re-run with OMI_ALLOW_UNTRUSTED_HOOKS=1." >&2
  exit 1
}

if [ "$HOOK_NAME" = "pre-push" ]; then
  if [ -x "$ROOT/scripts/pre-push-singleflight" ]; then
    assert_trusted_hook_script scripts/pre-push-singleflight
    assert_trusted_hook_script scripts/pre-push
    exec "$ROOT/scripts/pre-push-singleflight" "$@"
  fi
  # Older worktree branches may predate the single-flight wrapper even though
  # linked worktrees share this dispatcher. Keep their checked-in hook usable.
  assert_trusted_hook_script scripts/pre-push
  exec "$ROOT/scripts/pre-push" "$@"
fi
assert_trusted_hook_script "scripts/$HOOK_NAME"
exec "$ROOT/scripts/$HOOK_NAME" "$@"
HOOK
  chmod +x "$hook_path"
}

chmod +x \
  "$ROOT/scripts/changed-files" \
  "$ROOT/scripts/pre-commit" \
  "$ROOT/scripts/pre-push" \
  "$ROOT/scripts/pre-push-singleflight" \
  "$ROOT/scripts/pr-preflight"
install_dispatch_hook pre-commit
install_dispatch_hook pre-push

echo "Installed Git hook dispatchers in $HOOKS_DIR."
