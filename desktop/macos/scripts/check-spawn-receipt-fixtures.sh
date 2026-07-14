#!/usr/bin/env bash
# Static + semantic gate for desktop/macos/agent/fixtures/spawn-receipt/v1.
# Hermetic: Node/vitest only (no live app). Pair with Swift parse coverage in
# RealtimeHubSpawnAgentTests.testSharedSpawnReceiptFixturesAcceptValidAndRejectMalformed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_DIR="$DESKTOP_DIR/agent"
FIXTURE_DIR="$AGENT_DIR/fixtures/spawn-receipt/v1"

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

(
  cd "$AGENT_DIR"
  npm run build
  node node_modules/vitest/vitest.mjs run tests/spawn-receipt-fixtures.test.ts
)
