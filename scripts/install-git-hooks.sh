#!/usr/bin/env bash

set -euo pipefail

# Resolve the repo root from this script's own location. `git rev-parse
# --show-toplevel` fails ("this operation must be run in a work tree") in some
# linked-worktree layouts (e.g. a Conductor workspace whose gitdir lives under
# the main clone), which left ROOT empty and broke hook install. #10352
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
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

# Git runs hooks from the working-tree root, so PWD is the invoking worktree.
# Prefer --show-toplevel, but fall back to PWD: it fails in some linked-worktree
# layouts (Conductor workspaces), and an empty ROOT bypassed the gate. #10352
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$ROOT" ] || ROOT="$PWD"
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
