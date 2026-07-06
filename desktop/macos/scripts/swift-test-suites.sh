#!/bin/bash
# Runs Swift XCTest suites in isolated processes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

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

cd "$MACOS_DIR"

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
