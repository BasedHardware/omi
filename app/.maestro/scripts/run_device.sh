#!/usr/bin/env bash
set -euo pipefail

# Run device-dependent Maestro E2E tests
#
# ⚠️  REQUIRES PHYSICAL OMI DEVICE
# These tests require a physical Omi device powered on and in Bluetooth range.
#
# Usage:
#   bash .maestro/scripts/run_device.sh
#
# Prerequisites:
#   - Maestro CLI installed: brew install maestro
#   - App built and installed on device/simulator
#   - Omi device powered on and in Bluetooth range
#   - Bluetooth enabled on test device

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAESTRO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FLOWS_DIR="$MAESTRO_DIR/flows"

# Check Maestro is installed
if ! command -v maestro &> /dev/null; then
  echo "ERROR: Maestro CLI not found."
  echo "Install with: brew install maestro"
  echo "  or: curl -Ls 'https://get.maestro.mobile.dev' | bash"
  exit 1
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     OMI APP - DEVICE-DEPENDENT MAESTRO TESTS                ║"
echo "║     ⚠️  Requires physical Omi device                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

DEVICE_FLOWS=(
  "09_device_connection.yaml"
  "10_recording.yaml"
)

PASSED=0
FAILED=0
RESULTS=()

for flow in "${DEVICE_FLOWS[@]}"; do
  flow_path="$FLOWS_DIR/$flow"
  flow_name="${flow%.yaml}"

  if [[ ! -f "$flow_path" ]]; then
    echo "⚠ SKIP: $flow (file not found)"
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

# Summary
TOTAL=$((PASSED + FAILED))
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                      TEST SUMMARY                           ║"
echo "╠══════════════════════════════════════════════════════════════╣"
for result in "${RESULTS[@]}"; do
  printf "║  %-56s  ║\n" "$result"
done
echo "╠══════════════════════════════════════════════════════════════╣"
printf "║  Total: %-3d | Passed: %-3d | Failed: %-3d                   ║\n" \
  "$TOTAL" "$PASSED" "$FAILED"
echo "╚══════════════════════════════════════════════════════════════╝"

if [[ "$FAILED" -gt 0 ]]; then
  exit 1
fi
