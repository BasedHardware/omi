#!/usr/bin/env bash

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
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

ROOT="$(git rev-parse --show-toplevel)"
HOOK_NAME="$(basename "$0")"
if [ "$HOOK_NAME" = "pre-push" ]; then
  exec "$ROOT/scripts/pre-push-singleflight" "$@"
fi
exec "$ROOT/scripts/$HOOK_NAME" "$@"
HOOK
  chmod +x "$hook_path"
}

chmod +x "$ROOT/scripts/pre-commit" "$ROOT/scripts/pre-push" "$ROOT/scripts/pre-push-singleflight" "$ROOT/scripts/pr-preflight"
install_dispatch_hook pre-commit
install_dispatch_hook pre-push

echo "Installed Git hook dispatchers in $HOOKS_DIR."
