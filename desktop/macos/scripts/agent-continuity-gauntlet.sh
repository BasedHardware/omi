#!/usr/bin/env bash
# Agent continuity gauntlet — standing INV-6 smoke test for the desktop agent refactor.
#
# LIVE suites (this script) cover bridge/LLM continuity on a named bundle.
# HERMETIC INV-6 write-path rules (stage/promote single-writer, floating snapshot
# alias, open-by-id hydrate, viewport SoT) live in Swift unit tests gated by
# agent-logic-harness.sh + gauntlet --self-check. See AGENTS.md →
# "Live gauntlet vs hermetic INV-6 coverage".
#
# Drives a named omi-* bundle through:
#   0. (non-prod) clear kernel main_chat turns to avoid stale model-visible history
#   1. typed main-chat turn
#   2. PTT hub turn (ptt_test_turn + forced transcript)
#   3. typed follow-up that must see the PTT turn
#   4. background agent spawn (spawn_agent)
#   5. status query about that spawned agent
#   7. floating pill spawn → cross-surface blind recall (PTT + typed)
#   R. optional resilience suite: startup/bad-state bridge + R3 race + R4 subagent
#
# Repeated runs on one bundle pollute model-visible history even though R8 per-run
# nonces protect harness assertions. Step 0 clears kernel turns via the real bridge.
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
#   ./scripts/agent-continuity-gauntlet.sh --suite prompts       # fast typed-only prompt probes (P1-P3)
#   ./scripts/agent-continuity-gauntlet.sh --suite continuity    # steps 1-3 only (includes PTT)
#   ./scripts/agent-continuity-gauntlet.sh --suite resilience    # startup/resilience probes (R1-R4)
#   ./scripts/agent-continuity-gauntlet.sh --suite all           # core + prompt + resilience probes
#   OMI_AUTOMATION_PORT=47778 ./scripts/agent-continuity-gauntlet.sh --bundle-id com.omi.omi-gauntlet
#   ./scripts/agent-continuity-gauntlet.sh --turn-timeout-ms 240000
#
# Release-candidate manual QA: run --suite resilience first for startup edges,
# then --suite all for the full canonical continuity + resilience pass.
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
