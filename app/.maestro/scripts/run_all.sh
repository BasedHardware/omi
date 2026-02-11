#!/usr/bin/env bash
set -euo pipefail

# Run all Maestro E2E functional tests (excluding device-dependent flows)
#
# Usage:
#   bash .maestro/scripts/run_all.sh [--report]
#
# Prerequisites:
#   - Maestro CLI installed: brew install maestro
#   - App built and installed on device/simulator
#   - Device/simulator is running
#
# Options:
#   --report    Generate HTML report in .maestro/report/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAESTRO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FLOWS_DIR="$MAESTRO_DIR/flows"
REPORT_DIR="$MAESTRO_DIR/report"

GENERATE_REPORT=false
for arg in "$@"; do
  if [[ "$arg" == "--report" ]]; then
    GENERATE_REPORT=true
  fi
done

# Check Maestro is installed
if ! command -v maestro &> /dev/null; then
  echo "ERROR: Maestro CLI not found."
  echo "Install with: brew install maestro"
  echo "  or: curl -Ls 'https://get.maestro.mobile.dev' | bash"
  exit 1
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         OMI APP - MAESTRO FUNCTIONAL TESTS                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Core flows (no device required)
CORE_FLOWS=(
  "01_onboarding.yaml"
  "02_conversations_list.yaml"
  "03_conversation_detail.yaml"
  "04_conversation_crud.yaml"
  "05_memories.yaml"
  "06_chat.yaml"
  "07_apps.yaml"
  "08_settings.yaml"
)

PASSED=0
FAILED=0
SKIPPED=0
RESULTS=()

for flow in "${CORE_FLOWS[@]}"; do
  flow_path="$FLOWS_DIR/$flow"
  flow_name="${flow%.yaml}"

  if [[ ! -f "$flow_path" ]]; then
    echo "⚠ SKIP: $flow (file not found)"
    SKIPPED=$((SKIPPED + 1))
    RESULTS+=("SKIP  $flow_name")
    continue
  fi

  echo "────────────────────────────────────────────────"
  echo "Running: $flow_name"
  echo "────────────────────────────────────────────────"

  if maestro test "$flow_path"; then
    echo "✓ PASS: $flow_name"
    PASSED=$((PASSED + 1))
    RESULTS+=("PASS  $flow_name")
  else
    echo "✗ FAIL: $flow_name"
    FAILED=$((FAILED + 1))
    RESULTS+=("FAIL  $flow_name")
  fi
  echo ""
done

# Generate HTML report if requested
if [[ "$GENERATE_REPORT" == "true" ]]; then
  echo "────────────────────────────────────────────────"
  echo "Generating HTML report..."
  echo "────────────────────────────────────────────────"
  mkdir -p "$REPORT_DIR"
  maestro test "$FLOWS_DIR" \
    --include-tags="" \
    --exclude-tags="device_required" \
    --format html \
    --output "$REPORT_DIR/" || true
  echo "Report saved to: $REPORT_DIR/"
fi

# Summary
TOTAL=$((PASSED + FAILED + SKIPPED))
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                      TEST SUMMARY                           ║"
echo "╠══════════════════════════════════════════════════════════════╣"
for result in "${RESULTS[@]}"; do
  printf "║  %-56s  ║\n" "$result"
done
echo "╠══════════════════════════════════════════════════════════════╣"
printf "║  Total: %-3d | Passed: %-3d | Failed: %-3d | Skipped: %-3d   ║\n" \
  "$TOTAL" "$PASSED" "$FAILED" "$SKIPPED"
echo "╚══════════════════════════════════════════════════════════════╝"

if [[ "$FAILED" -gt 0 ]]; then
  exit 1
fi
