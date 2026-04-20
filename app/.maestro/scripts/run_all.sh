#!/usr/bin/env bash
#
# Run all Maestro E2E tests for the Omi app.
#
# Usage:
#   ./run_all.sh                   # Run all flows on connected device
#   ./run_all.sh --tags smoke      # Run only smoke tests
#   ./run_all.sh --platform ios    # Target iOS simulator
#   ./run_all.sh --report          # Generate HTML report
#
# Prerequisites:
#   1. Install Maestro: curl -Ls "https://get.maestro.mobile.dev" | bash
#   2. Connect device or start emulator:
#      Android: adb devices (should show device)
#      iOS:     xcrun simctl list | grep Booted
#   3. Build and install the dev app:
#      cd app && flutter build apk --flavor dev && adb install build/app/outputs/flutter-apk/app-dev-release.apk
#
# Environment variables (override defaults in config.yaml):
#   TEST_USER_NAME       Name for onboarding test
#   TEST_MEMORY_TITLE    Title for memory creation test
#   TEST_CHAT_QUESTION   Question for chat test

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAESTRO_DIR="$(dirname "$SCRIPT_DIR")"
FLOWS_DIR="$MAESTRO_DIR/flows"
REPORT_DIR="$MAESTRO_DIR/reports"

# Parse arguments
TAGS=""
PLATFORM="android"
REPORT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --tags) TAGS="$2"; shift 2 ;;
        --platform) PLATFORM="$2"; shift 2 ;;
        --report) REPORT=true; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# Verify maestro is installed
if ! command -v maestro &>/dev/null; then
    echo "Error: maestro not found. Install: curl -Ls 'https://get.maestro.mobile.dev' | bash"
    exit 1
fi

echo "╔══════════════════════════════════════════════╗"
echo "║  Omi Maestro E2E Test Suite                 ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Platform:  $PLATFORM"
echo "Tags:      ${TAGS:-all}"
echo "Report:    $REPORT"
echo ""

# Set platform env
export PLATFORM="$PLATFORM"

# Build flow list
FLOW_FILES=()
if [[ -n "$TAGS" ]]; then
    # Filter by tag (grep YAML files for the tag)
    for f in "$FLOWS_DIR"/*.yaml; do
        if grep -q "- $TAGS" "$f" 2>/dev/null; then
            FLOW_FILES+=("$f")
        fi
    done
else
    FLOW_FILES=("$FLOWS_DIR"/*.yaml)
fi

echo "Running ${#FLOW_FILES[@]} flow(s)..."
echo ""

# Run each flow
PASSED=0
FAILED=0
RESULTS=()

for flow in "${FLOW_FILES[@]}"; do
    flow_name=$(basename "$flow" .yaml)
    echo -n "  [$flow_name] ... "

    if maestro test "$flow" --no-ansi 2>/dev/null; then
        echo "✅ PASS"
        PASSED=$((PASSED + 1))
        RESULTS+=("PASS: $flow_name")
    else
        echo "❌ FAIL"
        FAILED=$((FAILED + 1))
        RESULTS+=("FAIL: $flow_name")
    fi
done

echo ""
echo "════════════════════════════════════════════════"
echo "  Results: $PASSED passed, $FAILED failed (${#FLOW_FILES[@]} total)"
echo "════════════════════════════════════════════════"

# Generate report if requested
if [[ "$REPORT" == true ]]; then
    mkdir -p "$REPORT_DIR"
    REPORT_FILE="$REPORT_DIR/report_$(date +%Y%m%d_%H%M%S).txt"
    {
        echo "Omi Maestro E2E Test Report"
        echo "Date: $(date)"
        echo "Platform: $PLATFORM"
        echo ""
        for r in "${RESULTS[@]}"; do echo "  $r"; done
        echo ""
        echo "Total: $PASSED passed, $FAILED failed"
    } > "$REPORT_FILE"
    echo ""
    echo "Report saved: $REPORT_FILE"
fi

# Exit with failure if any test failed
[[ $FAILED -eq 0 ]] && exit 0 || exit 1
