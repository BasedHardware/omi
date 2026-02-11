#!/usr/bin/env bash
set -euo pipefail

# Omi App Performance Test Suite Runner
#
# Runs all performance integration tests and generates a summary report.
#
# Usage:
#   bash scripts/run_performance_tests.sh [device_id]
#
# Prerequisites:
#   - Flutter SDK installed
#   - Physical device connected (recommended) or simulator running
#   - App dependencies resolved (flutter pub get)
#
# Arguments:
#   device_id   Optional device ID. If not provided, uses the first available device.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

DEVICE_ID="${1:-}"
DEVICE_FLAG=""
if [[ -n "$DEVICE_ID" ]]; then
  DEVICE_FLAG="-d $DEVICE_ID"
fi

export PERF_REPORT_DIR="/tmp/omi_perf_reports"
mkdir -p "$PERF_REPORT_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_FILE="$PERF_REPORT_DIR/performance_report_$TIMESTAMP.md"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         OMI APP PERFORMANCE TEST SUITE                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Report directory: $PERF_REPORT_DIR"
echo ""

TESTS=(
  "performance_memory_test.dart:Memory Leak Detection"
  "performance_cpu_test.dart:CPU Load Profiling"
  "performance_responsiveness_test.dart:Responsiveness & Jank"
  "performance_battery_test.dart:Battery Drain Estimation"
)

PASSED=0
FAILED=0
RESULTS=()

for test_entry in "${TESTS[@]}"; do
  IFS=':' read -r test_file test_name <<< "$test_entry"

  echo "────────────────────────────────────────────────"
  echo "Running: $test_name ($test_file)"
  echo "────────────────────────────────────────────────"

  if flutter drive \
    --driver=test_driver/perf_test_driver.dart \
    --target=integration_test/"$test_file" \
    --profile \
    --flavor dev \
    $DEVICE_FLAG 2>&1 | tee "$PERF_REPORT_DIR/${test_file%.dart}_$TIMESTAMP.log"; then
    echo "PASS: $test_name"
    PASSED=$((PASSED + 1))
    RESULTS+=("PASS|$test_name")
  else
    echo "FAIL: $test_name"
    FAILED=$((FAILED + 1))
    RESULTS+=("FAIL|$test_name")
  fi
  echo ""
done

# Generate markdown report using the Dart report generator
echo "Generating performance report..."
dart "$ROOT_DIR/scripts/perf_report.dart" "$REPORT_FILE"

# Summary
TOTAL=$((PASSED + FAILED))
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                 PERFORMANCE TEST SUMMARY                    ║"
echo "╠══════════════════════════════════════════════════════════════╣"
for result in "${RESULTS[@]}"; do
  IFS='|' read -r status name <<< "$result"
  printf "║  %-4s  %-52s  ║\n" "$status" "$name"
done
echo "╠══════════════════════════════════════════════════════════════╣"
printf "║  Total: %-3d | Passed: %-3d | Failed: %-3d                   ║\n" \
  "$TOTAL" "$PASSED" "$FAILED"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Report saved to: $REPORT_FILE"

if [[ "$FAILED" -gt 0 ]]; then
  exit 1
fi
