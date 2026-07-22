#!/usr/bin/env bash
# Manifest lane for agent-cloud: install pinned deps and run the vitest suite
# (unit tests + the hermetic WS e2e, which uses the scripted SDK fixture and
# needs no network or live model).
set -euo pipefail
cd "$(dirname "$0")/.."

node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [[ "$node_major" -lt 20 || "$node_major" -gt 24 ]]; then
  echo "agent-cloud tests need Node 20-24 (better-sqlite3 prebuilds); found $node_major" >&2
  exit 1
fi

npm ci --no-audit --no-fund
npm test
