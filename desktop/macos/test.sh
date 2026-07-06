#!/bin/bash
# Desktop test runner — runs both Rust backend and Swift app tests.
# Usage: cd desktop && bash test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Desktop Launcher Script Tests ==="
cd "$SCRIPT_DIR"
bash tests/test-app-config.sh
bash tests/test-settings-seed.sh
bash tests/test-cleanup-omi-tcc.sh
bash tests/test-omi-harness.sh
echo ""

echo "=== Rust Backend Tests ==="
cd "$SCRIPT_DIR/Backend-Rust"
cargo test
echo ""

echo "=== Swift App Tests (per-suite process isolation) ==="
cd "$SCRIPT_DIR"
# Each XCTest suite runs in its own `swift test --filter` process.
#
# Why: many suites share process-global singletons (RewindDatabase.shared,
# MemoryStorage.shared, AuthState.shared, StagedTaskStorage.shared), a real
# on-disk SQLite, and UserDefaults. In a single combined `swift test` run that
# state leaks across suites and hard-crashes a co-scheduled memory/storage suite.
# The crash is a scheduling-dependent moving target, so no fixed --skip set makes
# the combined run deterministic. Every suite passes in isolation, so we isolate
# each — mirroring the backend's per-file pytest isolation.
# Tracking: https://github.com/BasedHardware/omi/issues/9029
# (durable fix is singleton dependency injection; see the same issue).
#
# Method-level skips in scripts/swift-test-suites.sh are the only remaining
# known-red tests; each needs a product/policy decision, not a test change:
#   ChatDiscoverabilityTests/{testAgentControlCapabilitiesMatchCanonicalManifest,
#     testDesktopCapabilitiesExistInAgentToolDeclarations,
#     testDesktopPromptDistinguishesDelegationFromFloatingPills}
#       — Swift DesktopCapabilityRegistry vs agent control-tool-manifest.ts vs the
#         desktop chat prompt have drifted; reconciling the canonical tool set is a
#         product change. https://github.com/BasedHardware/omi/issues/9030
#   APIClientRoutingTests/testDeleteConversationRoutesToPython
#       — client omits ?cascade=true; cascade is backend-gated behind owner sign-off
#         (backend/routers/conversations.py), so flipping it is a data-deletion
#         behavior change, not a test fix. https://github.com/BasedHardware/omi/issues/9031
#   ActionItemsFTSRepairTests/testRepairToleratesMissingActionItemsFTSShadowTable
#       — macOS 26 system SQLite rejects `DELETE FROM sqlite_master` even with
#         writable_schema=ON, blocking the test's corruption setup.
#         https://github.com/BasedHardware/omi/issues/9032
"$SCRIPT_DIR/scripts/swift-test-suites.sh"
echo ""

echo "All desktop tests passed."
