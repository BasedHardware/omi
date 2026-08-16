#!/usr/bin/env bash
# LIFECYCLE: permanent
# Memory continuity gauntlet — standing INV-MEM smoke test for canonical memory tiers.
#
# HERMETIC pipeline rules (capture→promote→recall, archive exclusion, surface
# default-access, fail-closed resilience) also live in
# testing/e2e/test_canonical_memory_pipeline.py + gauntlet --self-check.
# See backend/AGENTS.md → "Memory continuity gauntlet gates".
#
# LIVE suites exercise a running backend with ADMIN_KEY when available.
# Without credentials the driver falls back to hermetic fakes / TestClient, or
# records suites as NOT_RUN when --live is requested.
#
# Evidence bundle (timestamped under backend/.harness/memory-continuity-gauntlet/):
#   manifest.json with per-suite status, mode, structural assertions, nonces.
#
# Usage:
#   python3 backend/scripts/memory-continuity-gauntlet.py --self-check
#   ./backend/scripts/memory-continuity-gauntlet.sh
#   ./backend/scripts/memory-continuity-gauntlet.sh --suite capture,promote,recall
#   MEM_GAUNTLET_API_URL=http://127.0.0.1:8080 ./backend/scripts/memory-continuity-gauntlet.sh --live
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

exec python3 "$SCRIPT_DIR/memory-continuity-gauntlet.py" "$@"
