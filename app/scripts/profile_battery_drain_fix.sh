#!/bin/bash
#
# Battery Drain Fix Profiling Script (PR #4440)
#
# Profiles the widget rebuild reduction from Consumer→Selector changes.
# Measures CPU activity and rebuild counts before/after the fix.
#
# What this PR fixes:
#   - LiteCaptureWidget: Consumer→Selector (rebuild on segments/photos only)
#   - BatteryInfoWidget: Consumer→Selector (rebuild on battery/device/connecting only)
#   - Battery level throttling: >=5% delta, 15min elapsed, or 20% threshold crossing
#   - metricsNotifyEnabled flag: disabled by default, enabled by widgets that need it
#
# Usage:
#   ./scripts/profile_battery_drain_fix.sh [base_branch] [test_branch]
#
# Example:
#   ./scripts/profile_battery_drain_fix.sh main fix/battery-drain-consumer-rebuilds-4437
#
# Requirements:
#   - Android device connected (adb devices)
#   - Flutter SDK in PATH
#   - Device must be in profile mode capable state
#

set -e

BASE_BRANCH="${1:-main}"
TEST_BRANCH="${2:-HEAD}"
RESULTS_DIR="/tmp/omi_battery_drain_profile"
DEVICE_ID="${DEVICE_ID:-}"
TRACE_DURATION_SEC=30
PACKAGE_NAME="com.friend.ios.dev"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║      BATTERY DRAIN FIX PROFILING (PR #4440)                  ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_section() {
    echo ""
    echo -e "${CYAN}=== $1 ===${NC}"
}

# Create results directory
setup_dirs() {
    mkdir -p "$RESULTS_DIR"
    mkdir -p "$RESULTS_DIR/traces"
    mkdir -p "$RESULTS_DIR/logs"
}

# Get device ID if not specified
detect_device() {
    if [ -z "$DEVICE_ID" ]; then
        DEVICE_ID=$(adb devices | grep -v "List" | grep "device$" | head -1 | awk '{print $1}')
        if [ -z "$DEVICE_ID" ]; then
            echo -e "${RED}Error: No Android device found. Connect a device or set DEVICE_ID${NC}"
            exit 1
        fi
    fi
    echo "Device: $DEVICE_ID"
}

# Build and install app in profile mode
build_and_install() {
    local branch=$1
    print_section "Building $branch in profile mode"

    flutter pub get > /dev/null 2>&1
    flutter build apk --profile --flavor dev 2>&1 | tail -5

    print_section "Installing on device"
    adb -s "$DEVICE_ID" install -r build/app/outputs/flutter-apk/app-dev-profile.apk 2>&1 | tail -2
}

# Capture Perfetto trace for CPU/scheduler analysis
capture_perfetto_trace() {
    local output_name=$1
    local trace_file="$RESULTS_DIR/traces/${output_name}.perfetto-trace"

    print_section "Capturing Perfetto trace ($TRACE_DURATION_SEC seconds)"
    echo "Starting trace... reproduce the scenario during this time."

    # Use the project's perfetto config
    local config_file="$(dirname "$0")/../.claude/skills/flutter-android-profiling/references/perfetto-config.pbtxt"
    if [ ! -f "$config_file" ]; then
        # Fallback: create minimal config
        config_file="/tmp/perfetto_config.pbtxt"
        cat > "$config_file" << 'PERFETTO_CONFIG'
buffers { size_kb: 65536 fill_policy: RING_BUFFER }
data_sources {
  config {
    name: "linux.ftrace"
    ftrace_config {
      ftrace_events: "sched/sched_switch"
      ftrace_events: "power/cpu_frequency"
      atrace_categories: "gfx"
      atrace_categories: "view"
      atrace_categories: "sched"
      atrace_apps: "*"
    }
  }
}
data_sources { config { name: "android.surfaceflinger.frametimeline" } }
PERFETTO_CONFIG
    fi

    adb -s "$DEVICE_ID" shell "perfetto -o /data/misc/perfetto-traces/trace.perfetto-trace -t ${TRACE_DURATION_SEC}s -c - < /dev/null" &
    sleep "$TRACE_DURATION_SEC"

    adb -s "$DEVICE_ID" pull /data/misc/perfetto-traces/trace.perfetto-trace "$trace_file" 2>/dev/null || true

    if [ -f "$trace_file" ]; then
        echo "Trace saved: $trace_file"
    else
        echo -e "${YELLOW}Warning: Could not pull perfetto trace${NC}"
    fi
}

# Capture logcat for widget rebuild tracking
capture_rebuild_logs() {
    local output_name=$1
    local log_file="$RESULTS_DIR/logs/${output_name}_rebuilds.log"

    print_section "Capturing widget rebuild logs"

    # Clear logcat and start fresh
    adb -s "$DEVICE_ID" logcat -c

    echo "Recording for $TRACE_DURATION_SEC seconds..."
    echo "Navigate the app: go to home screen, wait for battery updates, trigger transcript updates."

    # Capture flutter logs that contain rebuild info
    timeout "$TRACE_DURATION_SEC" adb -s "$DEVICE_ID" logcat -v time flutter:V *:S > "$log_file" 2>/dev/null || true

    echo "Logs saved: $log_file"
}

# Capture CPU usage using top
capture_cpu_stats() {
    local output_name=$1
    local stats_file="$RESULTS_DIR/logs/${output_name}_cpu.log"

    print_section "Capturing CPU statistics"

    # Get PID of the app
    local pid=$(adb -s "$DEVICE_ID" shell pidof "$PACKAGE_NAME" 2>/dev/null)
    if [ -z "$pid" ]; then
        echo -e "${YELLOW}Warning: App not running, skipping CPU capture${NC}"
        return
    fi

    echo "App PID: $pid"
    echo "Recording CPU usage for $TRACE_DURATION_SEC seconds..."

    # Sample CPU every 2 seconds
    for i in $(seq 1 $((TRACE_DURATION_SEC / 2))); do
        echo "=== Sample $i at $(date +%H:%M:%S) ===" >> "$stats_file"
        adb -s "$DEVICE_ID" shell "top -b -n 1 -p $pid" 2>/dev/null | grep -E "^[[:space:]]*$pid|%CPU" >> "$stats_file" || true
        sleep 2
    done

    echo "CPU stats saved: $stats_file"
}

# Run simpleperf for CPU profiling
capture_simpleperf() {
    local output_name=$1
    local perf_file="$RESULTS_DIR/traces/${output_name}_perf.data"

    print_section "Capturing simpleperf CPU profile"

    local pid=$(adb -s "$DEVICE_ID" shell pidof "$PACKAGE_NAME" 2>/dev/null)
    if [ -z "$pid" ]; then
        echo -e "${YELLOW}Warning: App not running, skipping simpleperf${NC}"
        return
    fi

    echo "Profiling PID $pid for $TRACE_DURATION_SEC seconds..."

    adb -s "$DEVICE_ID" shell "simpleperf record -p $pid -f 1000 --duration $TRACE_DURATION_SEC -o /data/local/tmp/perf.data" 2>/dev/null || {
        echo -e "${YELLOW}Warning: simpleperf not available or failed${NC}"
        return
    }

    adb -s "$DEVICE_ID" pull /data/local/tmp/perf.data "$perf_file" 2>/dev/null || true

    if [ -f "$perf_file" ]; then
        echo "Perf data saved: $perf_file"
    fi
}

# Analyze results
analyze_cpu_stats() {
    local file=$1
    local label=$2

    if [ ! -f "$file" ]; then
        echo "  (no data)"
        return
    fi

    # Extract CPU percentages and calculate average
    local avg_cpu=$(grep -E "^[[:space:]]*[0-9]+" "$file" | awk '{sum+=$9; count++} END {if(count>0) printf "%.1f", sum/count; else print "0"}')
    local max_cpu=$(grep -E "^[[:space:]]*[0-9]+" "$file" | awk 'BEGIN{max=0} {if($9>max) max=$9} END {printf "%.1f", max}')
    local samples=$(grep -c "=== Sample" "$file" || echo "0")

    echo "  Avg CPU: ${avg_cpu}%"
    echo "  Max CPU: ${max_cpu}%"
    echo "  Samples: $samples"
}

# Main profiling flow for a branch
profile_branch() {
    local branch=$1
    local output_name=$2

    echo -e "${YELLOW}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  PROFILING: $branch"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # Checkout and build
    git checkout "$branch" 2>/dev/null || git checkout -b "$branch" "origin/$branch" 2>/dev/null || {
        echo -e "${RED}Error: Could not checkout $branch${NC}"
        return 1
    }

    cd app
    build_and_install "$branch"

    # Launch app
    print_section "Launching app"
    adb -s "$DEVICE_ID" shell am start -n "$PACKAGE_NAME/.MainActivity" 2>/dev/null
    sleep 5  # Wait for app to start

    # Run captures in parallel
    echo ""
    echo -e "${GREEN}Starting profiling captures...${NC}"
    echo "Please interact with the app during the capture:"
    echo "  1. Stay on the home screen with transcript visible"
    echo "  2. Wait for battery level updates"
    echo "  3. Trigger some transcript/segment changes if possible"
    echo ""

    capture_cpu_stats "$output_name" &
    local cpu_pid=$!

    capture_rebuild_logs "$output_name" &
    local log_pid=$!

    # Wait for captures
    wait $cpu_pid 2>/dev/null || true
    wait $log_pid 2>/dev/null || true

    # Optional: Perfetto trace (may require root)
    # capture_perfetto_trace "$output_name"

    cd ..
    echo ""
}

# Compare and report results
generate_report() {
    print_section "COMPARISON REPORT"

    echo ""
    echo "=== BASE BRANCH ($BASE_BRANCH) ==="
    analyze_cpu_stats "$RESULTS_DIR/logs/base_cpu.log" "Base"

    echo ""
    echo "=== TEST BRANCH ($TEST_BRANCH) ==="
    analyze_cpu_stats "$RESULTS_DIR/logs/test_cpu.log" "Test"

    echo ""
    echo "=== EXPECTED IMPROVEMENTS ==="
    echo "  - LiteCaptureWidget: rebuilds only on segments/photos change"
    echo "  - BatteryInfoWidget: rebuilds only on battery/device/connecting change"
    echo "  - Battery notifications: throttled to >=5% delta or 15min interval"
    echo "  - Metrics timer: notifyListeners() skipped when no UI needs it"

    echo ""
    echo "=== VERIFICATION CHECKLIST ==="
    echo "  [ ] CPU usage lower in test branch during idle"
    echo "  [ ] Fewer rebuilds logged for LiteCaptureWidget"
    echo "  [ ] Fewer rebuilds logged for BatteryInfoWidget"
    echo "  [ ] Battery level changes don't trigger excessive rebuilds"

    echo ""
    echo "Results saved to: $RESULTS_DIR"
    echo ""
    echo "To analyze Perfetto traces:"
    echo "  1. Open https://ui.perfetto.dev"
    echo "  2. Load trace file from: $RESULTS_DIR/traces/"
    echo ""
}

# Main execution
main() {
    print_header
    echo "Base branch: $BASE_BRANCH"
    echo "Test branch: $TEST_BRANCH"

    setup_dirs
    detect_device

    # Store current branch
    ORIGINAL_BRANCH=$(git branch --show-current 2>/dev/null || echo "HEAD")

    # Profile base branch
    profile_branch "$BASE_BRANCH" "base"

    # Profile test branch
    profile_branch "$TEST_BRANCH" "test"

    # Return to original branch
    git checkout "$ORIGINAL_BRANCH" 2>/dev/null || true

    # Generate report
    generate_report
}

# Run main
main "$@"
