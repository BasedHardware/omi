#!/bin/bash
# Desktop test runner — runs both Rust backend and Swift app tests.
# Usage: cd desktop && bash test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Desktop Launcher Script Tests ==="
cd "$SCRIPT_DIR"
# Discovery, not a hardcoded list — a hardcoded list already orphaned one test
# (test-prepare-desktop-bundle-native-deps.sh ran nowhere). Every tests/test-*.sh
# runs, mirroring swift-test-suites.sh's auto-discovery of Swift suites.
for t in tests/test-*.sh; do
  echo "== $t"
  bash "$t"
done
python3 scripts/check-e2e-flow-coverage.py --strict
echo ""

echo "=== Rust Backend Tests ==="
cd "$SCRIPT_DIR/Backend-Rust"
cargo test
echo ""

echo "=== Swift App Tests (parallel per-suite process isolation) ==="
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
# Method-level skips are ratcheted in scripts/swift-test-skips.json so new
# known-red tests require an explicit issue, reason, and skip-count change.
"$SCRIPT_DIR/scripts/swift-test-suites.sh"
echo ""

echo "All desktop tests passed."
