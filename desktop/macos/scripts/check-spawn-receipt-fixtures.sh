#!/usr/bin/env bash
# Static + semantic gate for desktop/macos/agent/fixtures/spawn-receipt/v1.
# Hermetic: Node/vitest only (no live app). Pair with Swift parse coverage in
# RealtimeHubSpawnAgentTests.testSharedSpawnReceiptFixturesAcceptValidAndRejectMalformed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_DIR="$DESKTOP_DIR/agent"
FIXTURE_DIR="$AGENT_DIR/fixtures/spawn-receipt/v1"

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

  echo "ERROR: Node.js 22.6+ with --experimental-strip-types is required for spawn-receipt fixture tests." >&2
  echo "Install Node 22 or run desktop/macos/scripts/prepare-agent-runtime.sh first." >&2
  return 1
}

if [[ ! -d "$FIXTURE_DIR" ]]; then
  echo "missing spawn-receipt fixtures at $FIXTURE_DIR" >&2
  exit 1
fi

valid_count="$(find "$FIXTURE_DIR" -maxdepth 1 -type f -name 'valid-*.json' | wc -l | tr -d ' ')"
malformed_count="$(find "$FIXTURE_DIR" -maxdepth 1 -type f -name 'malformed-*.json' | wc -l | tr -d ' ')"
if [[ "$valid_count" -lt 1 || "$malformed_count" -lt 1 ]]; then
  echo "spawn-receipt v1 requires at least one valid-*.json and one malformed-*.json" >&2
  exit 1
fi
if [[ ! -f "$FIXTURE_DIR/README.md" ]]; then
  echo "spawn-receipt v1 README.md is required" >&2
  exit 1
fi

if [[ ! -d "$AGENT_DIR/node_modules" ]]; then
  (
    cd "$AGENT_DIR"
    npm ci --no-fund --no-audit
  )
fi

NODE22="$(select_node22)"
export PATH="$(dirname "$NODE22"):$PATH"

(
  cd "$AGENT_DIR"
  npm run build
  "$NODE22" node_modules/vitest/vitest.mjs run tests/spawn-receipt-fixtures.test.ts
)
