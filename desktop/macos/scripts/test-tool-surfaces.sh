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

ensure_npm_deps "$DESKTOP_DIR/agent"

(
  cd "$DESKTOP_DIR/agent"
  npm run build --silent
)

(
  cd "$DESKTOP_DIR/agent"
  npm test -- --run \
    tests/omi-tool-manifest.test.ts \
    tests/control-tools.test.ts \
    tests/node-tools.test.ts \
    tests/codemagic-pi-mono-extension-ci.test.ts
)

ensure_npm_deps "$DESKTOP_DIR/pi-mono-extension"
(
  cd "$DESKTOP_DIR/pi-mono-extension"
  node_bin="$DESKTOP_DIR/Desktop/Sources/Resources/node"
  if [[ -x "$node_bin" ]]; then
    "$node_bin" --experimental-strip-types --test index.test.ts
  elif node --experimental-strip-types --test index.test.ts; then
    echo "pi-mono-extension tests passed (native Node --experimental-strip-types)"
  else
    echo "Falling back to npx tsx for older Node versions..."
    npx --yes tsx@4.19.2 --test index.test.ts
  fi
)
