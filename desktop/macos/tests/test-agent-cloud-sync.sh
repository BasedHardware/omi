#!/usr/bin/env bash
# Runs the agent-cloud /sync end-to-end regression test (sync-e2e.mjs): the real
# agent.mjs server, a real SQLite file, and a desktop-shaped batch whose rows omit
# different NULL columns. Guards against the batch schema being taken from one row.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_CLOUD="$SCRIPT_DIR/../agent-cloud"

if ! command -v node > /dev/null 2>&1; then
  echo "SKIP: node not installed"
  exit 0
fi

# The VM's runtime deps are not vendored; install them on first run. Without them
# agent.mjs cannot start, so skip rather than fail an unrelated desktop change.
if [ ! -d "$AGENT_CLOUD/node_modules/better-sqlite3" ]; then
  if ! (cd "$AGENT_CLOUD" && npm install --no-audit --no-fund --silent); then
    echo "SKIP: could not install agent-cloud dependencies (node $(node -v))"
    exit 0
  fi
fi

(cd "$AGENT_CLOUD" && node sync-e2e.mjs)
