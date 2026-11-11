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
if [ "$HOOK_NAME" = "pre-push" ]; then
  if [ -x "$ROOT/scripts/pre-push-singleflight" ]; then
    exec "$ROOT/scripts/pre-push-singleflight" "$@"
  fi
  # Older worktree branches may predate the single-flight wrapper even though
  # linked worktrees share this dispatcher. Keep their checked-in hook usable.
  exec "$ROOT/scripts/pre-push" "$@"
fi
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
