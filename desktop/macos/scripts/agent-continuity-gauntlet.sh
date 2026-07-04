#!/usr/bin/env bash
# Agent continuity gauntlet — standing INV-6 smoke test for the desktop agent refactor.
#
# Drives a named omi-* bundle through:
#   1. typed main-chat turn
#   2. PTT hub turn (ptt_test_turn + forced transcript)
#   3. typed follow-up that must see the PTT turn
#   4. background agent spawn (spawn_agent)
#   5. status query about that spawned agent
#
# Evidence bundle (timestamped under desktop/macos/.harness/agent-continuity-gauntlet/):
#   per-step user/assistant text, QueryTracer excerpts, runtime sqlite path+hash,
#   app log excerpt, automation snapshots, optional agent-swift screenshot.
#
# Prerequisites (full E2E):
#   - macOS with a running named test bundle, e.g.:
#       cd desktop/macos && OMI_APP_NAME=omi-gauntlet OMI_SKIP_TUNNEL=1 ./run.sh
#   - Signed-in session (./scripts/omi-auth-seed.sh com.omi.omi-gauntlet before launch)
#   - LLM / realtime credentials available (BYOK or Omi account quota)
#   - Optional: brew install beastoin/tap/agent-swift (screenshots; gauntlet still runs without it)
#
# Usage:
#   cd desktop/macos && ./scripts/agent-continuity-gauntlet.sh
#   ./scripts/agent-continuity-gauntlet.sh --self-check          # validate hooks only
#   OMI_AUTOMATION_PORT=47778 ./scripts/agent-continuity-gauntlet.sh --bundle-id com.omi.omi-gauntlet
#   ./scripts/agent-continuity-gauntlet.sh --turn-timeout-ms 240000
#
# Also run via:
#   ./scripts/agent-logic-harness.sh --with-gauntlet
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "agent-continuity-gauntlet: full E2E requires macOS; running self-check only." >&2
  exec python3 "$SCRIPT_DIR/agent-continuity-gauntlet-lib.py" --self-check
fi

exec python3 "$SCRIPT_DIR/agent-continuity-gauntlet-lib.py" "$@"
