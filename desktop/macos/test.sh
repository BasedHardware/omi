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
# Method-level skips are the only remaining known-red tests; each needs a
# product/policy decision, not a test change:
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
#   PiMonoWiringTests/testLocalAgentProviderDetectorMissingPromptIsUserFacing
#       — the detector does not fully honor the injected environment/home, so the
#         result depends on whether OpenClaw is installed on the runner.
#         https://github.com/BasedHardware/omi/issues/9033
skip_for_suite() {
  case "$1" in
    ChatDiscoverabilityTests)
      echo "--skip ChatDiscoverabilityTests/testAgentControlCapabilitiesMatchCanonicalManifest --skip ChatDiscoverabilityTests/testDesktopCapabilitiesExistInAgentToolDeclarations --skip ChatDiscoverabilityTests/testDesktopPromptDistinguishesDelegationFromFloatingPills" ;;
    APIClientRoutingTests)
      echo "--skip APIClientRoutingTests/testDeleteConversationRoutesToPython" ;;
    ActionItemsFTSRepairTests)
      echo "--skip ActionItemsFTSRepairTests/testRepairToleratesMissingActionItemsFTSShadowTable" ;;
    PiMonoWiringTests)
      echo "--skip PiMonoWiringTests/testLocalAgentProviderDetectorMissingPromptIsUserFacing" ;;
  esac
}

# Discover suites recursively so tests in subfolders of Desktop/Tests are not
# silently skipped (SwiftPM compiles the whole Tests target; this must match).
suites=$(find Desktop/Tests -type f -name '*.swift' -print0 \
  | xargs -0 grep -hE '^(final )?class [A-Za-z0-9_]+: XCTestCase' \
  | sed -E 's/(final )?class ([A-Za-z0-9_]+):.*/\2/' | sort -u)
suite_log_dir="$(mktemp -d)"
trap 'rm -rf "$suite_log_dir"' EXIT
failed_suites=""
suite_count=0
while read -r suite; do
  [ -z "$suite" ] && continue
  suite_count=$((suite_count + 1))
  # shellcheck disable=SC2046
  if ! xcrun swift test --package-path Desktop --filter "${suite}/" $(skip_for_suite "$suite") \
      >"$suite_log_dir/$suite.log" 2>&1; then
    failed_suites="$failed_suites $suite"
    echo "--- FAILED: $suite ---"
    cat "$suite_log_dir/$suite.log"
  fi
done <<< "$suites"
echo "Ran $suite_count Swift suites in isolation."

if [ -n "$failed_suites" ]; then
  echo "FAILED Swift suites:$failed_suites"
  exit 1
fi
echo ""

echo "All desktop tests passed."
