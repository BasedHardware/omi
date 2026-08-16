#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ensure_npm_deps() {
  local dir="$1"
  if [[ -d "$dir/node_modules" ]]; then
    return
  fi
  (
    cd "$dir"
    npm ci --no-fund --no-audit
  )
}

node_supports_strip_types() {
  "$1" --experimental-strip-types -e '0' >/dev/null 2>&1
}

select_node22() {
  local node_bin
  local -a candidates=(
    "$DESKTOP_DIR/Desktop/Sources/Resources/node"
    "/opt/homebrew/opt/node@22/bin/node"
    "/usr/local/opt/node@22/bin/node"
  )

  if command -v brew >/dev/null 2>&1; then
    node_bin="$(brew --prefix node@22 2>/dev/null || true)"
    if [[ -n "$node_bin" ]]; then
      candidates+=("$node_bin/bin/node")
    fi
  fi

  node_bin="$(command -v node 2>/dev/null || true)"
  [[ -n "$node_bin" ]] && candidates+=("$node_bin")

  for node_bin in "${candidates[@]}"; do
    if [[ -x "$node_bin" ]] && node_supports_strip_types "$node_bin"; then
      printf '%s\n' "$node_bin"
      return
    fi
  done

  echo "ERROR: Node.js 22.6+ with --experimental-strip-types is required for desktop agent tool-surface tests." >&2
  echo "Install Node 22 or run desktop/macos/scripts/prepare-agent-runtime.sh first." >&2
  return 1
}

NODE22="$(select_node22)"
export PATH="$(dirname "$NODE22"):$PATH"

ensure_npm_deps "$DESKTOP_DIR/agent"

(
  cd "$DESKTOP_DIR/agent"
  npm run build --silent
)

(
  cd "$DESKTOP_DIR/agent"
  "$NODE22" --experimental-strip-types scripts/generate-tool-surfaces.mjs --check
)

(
  cd "$DESKTOP_DIR/agent"
  # The full runtime suite is the authoritative gate. A hand-picked list left
  # new execution-policy, persistence, transport, and routing regressions
  # compiled but never executed in CI.
  "$NODE22" node_modules/vitest/vitest.mjs run
)

ensure_npm_deps "$DESKTOP_DIR/pi-mono-extension"
(
  cd "$DESKTOP_DIR/pi-mono-extension"
  # tsx (not --experimental-strip-types): the manifest imports use ESM .js
  # specifiers for .ts files, which strip-types cannot resolve (G8).
  npx --yes tsx --test index.test.ts
)
