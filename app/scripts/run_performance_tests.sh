#!/usr/bin/env bash
#
# Omi Performance Test Suite Runner
# Issue: https://github.com/BasedHardware/omi/issues/3858
#
# Runs all performance tests and generates JSON + Markdown reports.
# Supports continuous 24-hour runs with hourly checkpoints.
#
# Usage:
#   bash app/scripts/run_performance_tests.sh [device_id] [options]
#
# Options:
#   --duration <hours>    Run duration in hours (default: 1, max: 24)
#   --output <dir>        Output directory for reports (default: /tmp/omi_perf_reports)
#   --quick               Quick mode: skip long-running tests
#   --test <name>         Run only a specific test (memory|battery|animation|shimmer|rebuild|app)
#   --flavor <flavor>     App flavor (default: dev)
#   --help                Show this help
#
# Examples:
#   bash app/scripts/run_performance_tests.sh              # 1-hour run, all tests
#   bash app/scripts/run_performance_tests.sh abc123        # specific device
#   bash app/scripts/run_performance_tests.sh --duration 24 # 24-hour continuous run
#   bash app/scripts/run_performance_tests.sh --quick       # fast smoke test
#   bash app/scripts/run_performance_tests.sh --test memory # only memory leak test

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEVICE_ID=""
DURATION_HOURS=1
OUTPUT_DIR="/tmp/omi_perf_reports"
QUICK_MODE=false
SINGLE_TEST=""
FLAVOR="dev"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# =============================================================================
# Argument Parsing
# =============================================================================

show_help() {
  head -25 "$0" | grep '^#' | sed 's/^# \?//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration)
      DURATION_HOURS="$2"
      shift 2
      ;;
    --output)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --quick)
      QUICK_MODE=true
      shift
      ;;
    --test)
      SINGLE_TEST="$2"
      shift 2
      ;;
    --flavor)
      FLAVOR="$2"
      shift 2
      ;;
    --help|-h)
      show_help
      ;;
    -*)
      echo "Unknown option: $1"
      show_help
      ;;
    *)
      DEVICE_ID="$1"
      shift
      ;;
  esac
done

# =============================================================================
# Setup
# =============================================================================

log() { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
log_ok() { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓${NC} $*"; }
log_warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠${NC} $*"; }
log_err() { echo -e "${RED}[$(date '+%H:%M:%S')] ✗${NC} $*"; }
log_section() {
  echo ""
  echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
  echo -e "${CYAN}  $*${NC}"
  echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
}

# Create output directory
mkdir -p "$OUTPUT_DIR"
RUN_ID="$(date '+%Y%m%d_%H%M%S')"
RUN_DIR="$OUTPUT_DIR/run_$RUN_ID"
mkdir -p "$RUN_DIR"

# Device flag
DEVICE_FLAG=""
if [[ -n "$DEVICE_ID" ]]; then
  DEVICE_FLAG="-d $DEVICE_ID"
fi

# Check for test_driver
DRIVER_DIR="$APP_DIR/test_driver"
if [[ ! -f "$DRIVER_DIR/integration_test.dart" ]]; then
  log "Creating test_driver/integration_test.dart..."
  mkdir -p "$DRIVER_DIR"
  cat > "$DRIVER_DIR/integration_test.dart" << 'DART'
import 'package:integration_test/integration_test_driver.dart';

Future<void> main() => integrationDriver();
DART
  log_ok "test_driver created"
fi

# =============================================================================
# Test Definitions
# =============================================================================

# Test names, files, and descriptions as parallel arrays (bash 3.2 compatible — macOS ships 3.2)
TEST_NAMES=("memory" "battery" "animation" "shimmer" "rebuild" "app")
TEST_FILES=(
  "integration_test/memory_leak_test.dart"
  "integration_test/battery_drain_test.dart"
  "integration_test/animation_performance_test.dart"
  "integration_test/shimmer_cpu_test.dart"
  "integration_test/widget_rebuild_profiling_test.dart"
  "integration_test/app_performance_test.dart"
)
TEST_DESCS=(
  "Memory leak detection (heap growth analysis)"
  "Battery drain estimation (CPU + frame cost profiling)"
  "Animation performance (frame timing)"
  "Shimmer CPU impact (static vs animated)"
  "Widget rebuild frequency (Selector vs Consumer)"
  "Full app performance (navigation + profiling)"
)

# Quick mode skips longer tests
QUICK_SKIP=("battery" "app")

# Lookup helpers for parallel arrays
_test_index() {
  local name="$1"
  for i in "${!TEST_NAMES[@]}"; do
    if [[ "${TEST_NAMES[$i]}" == "$name" ]]; then echo "$i"; return 0; fi
  done
  return 1
}
_test_file() { local i; i=$(_test_index "$1") && echo "${TEST_FILES[$i]}"; }
_test_desc() { local i; i=$(_test_index "$1") && echo "${TEST_DESCS[$i]}"; }

# =============================================================================
# Test Runner
# =============================================================================

run_single_test() {
  local name="$1"
  local test_file
  test_file=$(_test_file "$name")
  local log_file="$RUN_DIR/${name}.log"
  local result_file="$RUN_DIR/${name}.result"

  if [[ ! -f "$APP_DIR/$test_file" ]]; then
    log_warn "Test file not found: $test_file — skipping"
    echo "SKIP" > "$result_file"
    return 0
  fi

  log "Running: $(_test_desc "$name")"
  log "  File: $test_file"
  log "  Log:  $log_file"

  local start_time
  start_time=$(date +%s)

  # Run with flutter drive for real device/emulator profiling
  if cd "$APP_DIR" && flutter drive \
    --driver=test_driver/integration_test.dart \
    --target="$test_file" \
    --profile \
    --flavor "$FLAVOR" \
    $DEVICE_FLAG \
    2>&1 | tee "$log_file"; then
    echo "PASS" > "$result_file"
    local end_time
    end_time=$(date +%s)
    local elapsed=$((end_time - start_time))
    log_ok "$name completed in ${elapsed}s"
  else
    echo "FAIL" > "$result_file"
    local end_time
    end_time=$(date +%s)
    local elapsed=$((end_time - start_time))
    log_err "$name failed after ${elapsed}s (see $log_file)"
  fi

  return 0
}

get_tests_to_run() {
  if [[ -n "$SINGLE_TEST" ]]; then
    if ! _test_index "$SINGLE_TEST" >/dev/null; then
      log_err "Unknown test: $SINGLE_TEST"
      log "Available tests: ${TEST_NAMES[*]}"
      exit 1
    fi
    echo "$SINGLE_TEST"
    return
  fi

  # Order: quick tests first, then longer ones
  local order=("shimmer" "rebuild" "animation" "memory" "battery" "app")
  for name in "${order[@]}"; do
    if $QUICK_MODE; then
      local skip=false
      for s in "${QUICK_SKIP[@]}"; do
        if [[ "$name" == "$s" ]]; then
          skip=true
          break
        fi
      done
      if $skip; then
        continue
      fi
    fi
    echo "$name"
  done
}

# =============================================================================
# Report Generation
# =============================================================================

generate_report() {
  local checkpoint_label="${1:-final}"

  log_section "Generating reports ($checkpoint_label)"

  # --- JSON Report ---
  local json_file="$RUN_DIR/report_${checkpoint_label}.json"
  {
    echo "{"
    echo "  \"run_id\": \"$RUN_ID\","
    echo "  \"checkpoint\": \"$checkpoint_label\","
    echo "  \"timestamp\": \"$(date -u '+%Y-%m-%dT%H:%M:%SZ')\","
    echo "  \"config\": {"
    echo "    \"duration_hours\": $DURATION_HOURS,"
    echo "    \"quick_mode\": $QUICK_MODE,"
    echo "    \"flavor\": \"$FLAVOR\","
    echo "    \"device_id\": \"${DEVICE_ID:-auto}\""
    echo "  },"
    echo "  \"results\": {"

    local first=true
    for name in $(get_tests_to_run); do
      local result_file="$RUN_DIR/${name}.result"
      local status="NOT_RUN"
      if [[ -f "$result_file" ]]; then
        status=$(cat "$result_file")
      fi

      if ! $first; then echo ","; fi
      first=false

      echo -n "    \"$name\": {\"status\": \"$status\""

      # Include any JSON output from /tmp
      local latest_json
      latest_json=$(ls -t /tmp/omi_${name}*.json 2>/dev/null | head -1 || true)
      if [[ -n "$latest_json" && -f "$latest_json" ]]; then
        echo -n ", \"data_file\": \"$latest_json\""
        # Copy to run dir
        cp "$latest_json" "$RUN_DIR/" 2>/dev/null || true
      fi

      echo -n "}"
    done

    echo ""
    echo "  }"
    echo "}"
  } > "$json_file"
  log_ok "JSON report: $json_file"

  # --- Markdown Report ---
  local md_file="$RUN_DIR/report_${checkpoint_label}.md"
  {
    echo "# Omi Performance Test Report"
    echo ""
    echo "**Run ID:** $RUN_ID"
    echo "**Checkpoint:** $checkpoint_label"
    echo "**Timestamp:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "**Duration:** ${DURATION_HOURS}h | **Flavor:** $FLAVOR | **Device:** ${DEVICE_ID:-auto}"
    echo ""
    echo "## Results Summary"
    echo ""
    echo "| Test | Status | Description |"
    echo "|------|--------|-------------|"

    local pass_count=0
    local fail_count=0
    local skip_count=0

    for name in $(get_tests_to_run); do
      local result_file="$RUN_DIR/${name}.result"
      local status="NOT_RUN"
      if [[ -f "$result_file" ]]; then
        status=$(cat "$result_file")
      fi

      local icon="⏳"
      case "$status" in
        PASS) icon="✅"; ((pass_count++)) || true ;;
        FAIL) icon="❌"; ((fail_count++)) || true ;;
        SKIP) icon="⏭️"; ((skip_count++)) || true ;;
      esac

      echo "| $icon $name | $status | $(_test_desc "$name") |"
    done

    echo ""
    echo "**Summary:** $pass_count passed, $fail_count failed, $skip_count skipped"

    # Extract key metrics from logs
    echo ""
    echo "## Key Metrics"
    echo ""

    for name in $(get_tests_to_run); do
      local log_file="$RUN_DIR/${name}.log"
      if [[ ! -f "$log_file" ]]; then continue; fi

      echo "### $name"
      echo ""
      echo '```'
      # Extract the summary/results sections from test output
      grep -A 50 "FINAL SUMMARY\|MEMORY ANALYSIS\|BATTERY DRAIN REPORT\|TEST RESULTS\|REBUILD SUMMARY\|FRAME COST TREND\|WIDGET LEAK SUMMARY" "$log_file" \
        | head -60 \
        | sed 's/^.*║/║/' \
        | grep -v "^$" \
        || echo "(no summary found)"
      echo '```'
      echo ""
    done

    echo "---"
    echo ""
    echo "Report generated by \`run_performance_tests.sh\`"
    echo ""
    echo "Full logs: \`$RUN_DIR/\`"
  } > "$md_file"
  log_ok "Markdown report: $md_file"

  # Collect JSON data files from /tmp into run dir
  for f in /tmp/omi_memory_*.json /tmp/omi_battery_*.json /tmp/omi_frame_cost_*.json /tmp/omi_widget_leaks_*.json /tmp/omi_perf_*.csv; do
    if [[ -f "$f" ]]; then
      cp "$f" "$RUN_DIR/" 2>/dev/null || true
    fi
  done
}

# =============================================================================
# Main
# =============================================================================

main() {
  log_section "Omi Performance Test Suite"
  log "Run ID:      $RUN_ID"
  log "Duration:    ${DURATION_HOURS}h"
  log "Output:      $RUN_DIR"
  log "Quick mode:  $QUICK_MODE"
  log "Flavor:      $FLAVOR"
  log "Device:      ${DEVICE_ID:-auto-detect}"
  if [[ -n "$SINGLE_TEST" ]]; then
    log "Single test: $SINGLE_TEST"
  fi

  # Verify Flutter is available
  if ! command -v flutter &>/dev/null; then
    log_err "Flutter not found in PATH"
    exit 1
  fi

  # Verify we're in the right directory
  if [[ ! -f "$APP_DIR/pubspec.yaml" ]]; then
    log_err "pubspec.yaml not found in $APP_DIR"
    exit 1
  fi

  # Get tests to run
  local tests_list
  tests_list=$(get_tests_to_run)
  local test_count
  test_count=$(echo "$tests_list" | wc -w)
  log "Tests to run: $test_count"

  local total_start
  total_start=$(date +%s)
  local total_iterations=$((DURATION_HOURS))
  local current_iteration=0

  while [[ $current_iteration -lt $total_iterations ]]; do
    current_iteration=$((current_iteration + 1))

    log_section "Hour $current_iteration / $total_iterations"

    # Run all tests
    for name in $tests_list; do
      run_single_test "$name" || true
    done

    # Hourly checkpoint report
    generate_report "hour_${current_iteration}"

    # Check if we should continue (for multi-hour runs)
    local elapsed
    elapsed=$(( $(date +%s) - total_start ))
    local target_elapsed=$((current_iteration * 3600))

    if [[ $current_iteration -lt $total_iterations ]]; then
      if [[ $elapsed -lt $target_elapsed ]]; then
        local wait_time=$((target_elapsed - elapsed))
        log "Waiting ${wait_time}s until next hour checkpoint..."
        sleep "$wait_time"
      fi
    fi
  done

  # Final report
  generate_report "final"

  local total_elapsed
  total_elapsed=$(( $(date +%s) - total_start ))
  local total_min=$((total_elapsed / 60))

  log_section "Complete"
  log "Total time:  ${total_min} minutes"
  log "Reports:     $RUN_DIR/"
  log ""

  # Print pass/fail summary
  local pass=0 fail=0
  for name in $tests_list; do
    local result_file="$RUN_DIR/${name}.result"
    if [[ -f "$result_file" ]] && [[ "$(cat "$result_file")" == "PASS" ]]; then
      ((pass++)) || true
    else
      ((fail++)) || true
    fi
  done

  if [[ $fail -eq 0 ]]; then
    log_ok "All $pass tests passed"
  else
    log_err "$fail tests failed, $pass passed"
  fi

  log ""
  log "Reports:"
  ls -la "$RUN_DIR/"*.md "$RUN_DIR/"*.json 2>/dev/null | while read -r line; do
    log "  $line"
  done
}

main "$@"
