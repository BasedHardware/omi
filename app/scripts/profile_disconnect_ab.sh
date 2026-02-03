#!/usr/bin/env bash
set -euo pipefail

# A/B Profiling Comparison Script for Disconnect Issue
# Compares build 659 (071968072) vs current main branch
#
# Usage: ./profile_disconnect_ab.sh [duration_seconds]

PACKAGE="com.friend.ios.dev"
OUTPUT_DIR="profiling_results/disconnect_ab"
DURATION="${1:-120}"  # Default 2 minutes per branch
COMMIT_OLD="071968072"  # Build 659 with disconnect issues
COMMIT_NEW="HEAD"
PROFILING_BRANCH="profiling/disconnect-ab-comparison"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

mkdir -p "$OUTPUT_DIR"

# Check device is connected
check_device() {
    if ! adb devices | grep -q "device$"; then
        log_error "No Android device connected!"
        exit 1
    fi
    DEVICE_MODEL=$(adb shell getprop ro.product.model 2>/dev/null || echo "Unknown")
    ANDROID_VERSION=$(adb shell getprop ro.build.version.release 2>/dev/null || echo "Unknown")
    log_info "Device: $DEVICE_MODEL (Android $ANDROID_VERSION)"
}

# Save profiling patch
save_profiling_patch() {
    log_info "Saving profiling instrumentation patch..."
    git diff app/lib/providers/capture_provider.dart app/lib/providers/device_provider.dart > "$OUTPUT_DIR/profiling.patch" || true
}

# Apply profiling patch to a branch
apply_profiling_patch() {
    if [[ -f "$OUTPUT_DIR/profiling.patch" ]]; then
        log_info "Applying profiling patch..."
        git apply "$OUTPUT_DIR/profiling.patch" 2>/dev/null || {
            log_warn "Patch apply failed - may have conflicts, trying with 3-way merge"
            git apply --3way "$OUTPUT_DIR/profiling.patch" 2>/dev/null || {
                log_warn "Patch could not be applied cleanly"
                return 1
            }
        }
    fi
}

# Build Flutter APK in profile mode
build_apk() {
    local label="$1"
    log_info "Building APK for $label..."
    cd app
    flutter clean > /dev/null 2>&1 || true
    flutter pub get > /dev/null 2>&1
    flutter build apk --profile --flavor dev -t lib/main.dart 2>&1 | tail -5
    cd ..
    log_success "APK built for $label"
}

# Install APK (handles version downgrade)
install_apk() {
    local label="$1"
    log_info "Installing APK for $label..."
    adb uninstall "$PACKAGE" 2>/dev/null || true
    adb install -r app/build/app/outputs/flutter-apk/app-dev-profile.apk
    log_success "APK installed for $label"
}

# Launch app
launch_app() {
    log_info "Launching app..."
    adb shell am start -n "$PACKAGE/.MainActivity" > /dev/null
    sleep 3
}

# CPU sample
cpu_sample() {
    adb shell top -n 1 -b 2>/dev/null | grep "$PACKAGE" | awk '{print $9}' | head -1 || echo "0"
}

# Profile a branch
profile_branch() {
    local label="$1"
    local cpu_log="$OUTPUT_DIR/${label}_cpu_samples.csv"
    local events_log="$OUTPUT_DIR/${label}_events.log"

    echo "timestamp,cpu_percent" > "$cpu_log"

    log_info "=== Profiling: $label ==="
    log_info "Waiting for first segment event (connect device and start recording)..."

    # Clear logcat
    adb logcat -c

    # Wait for first profiling event or timeout after 60s
    local wait_count=0
    while true; do
        if adb logcat -d 2>/dev/null | grep -q "\[PROFILING\]"; then
            log_success "First profiling event detected!"
            break
        fi
        wait_count=$((wait_count + 1))
        if [[ $wait_count -gt 120 ]]; then
            log_warn "Timeout waiting for events, starting anyway..."
            break
        fi
        printf "\r  Waiting... %ds" "$wait_count"
        sleep 0.5
    done
    echo ""

    local start_time=$(date +%s)
    log_info "Recording for ${DURATION}s..."

    # Sample CPU every second
    for i in $(seq 1 "$DURATION"); do
        local cpu=$(cpu_sample)
        local timestamp=$(date +%s)
        echo "$timestamp,$cpu" >> "$cpu_log"

        local segments=$(adb logcat -d 2>/dev/null | grep -c "SEGMENT_RECEIVED" || echo "0")
        local disconnects=$(adb logcat -d 2>/dev/null | grep -c "DEVICE_DISCONNECTED" || echo "0")
        local reconnects=$(adb logcat -d 2>/dev/null | grep -c "DEVICE_CONNECTED" || echo "0")

        printf "\r  [%3ds/%ds] CPU: %5s%% | Segments: %3s | Disconnects: %2s | Reconnects: %2s" \
            "$i" "$DURATION" "$cpu" "$segments" "$disconnects" "$reconnects"
        sleep 1
    done
    echo ""

    # Save full profiling log
    adb logcat -d | grep "\[PROFILING\]" > "$events_log" 2>/dev/null || true

    # Calculate metrics
    local avg_cpu=$(awk -F',' 'NR>1 {sum+=$2; count++} END {if(count>0) printf "%.2f", sum/count; else print "0"}' "$cpu_log")
    local max_cpu=$(awk -F',' 'NR>1 {if($2>max) max=$2} END {print max+0}' "$cpu_log")
    local total_segments=$(grep -c "SEGMENT_RECEIVED" "$events_log" 2>/dev/null || echo "0")
    local total_disconnects=$(grep -c "DEVICE_DISCONNECTED" "$events_log" 2>/dev/null || echo "0")
    local total_reconnects=$(grep -c "DEVICE_CONNECTED" "$events_log" 2>/dev/null || echo "0")

    # Calculate average segment processing time
    local avg_segment_time=$(grep "processingTimeUs" "$events_log" 2>/dev/null | \
        sed 's/.*processingTimeUs: \([0-9]*\).*/\1/' | \
        awk '{sum+=$1; count++} END {if(count>0) printf "%.0f", sum/count; else print "0"}')

    log_success "Results for $label:"
    echo "  Average CPU: ${avg_cpu}%"
    echo "  Max CPU: ${max_cpu}%"
    echo "  Total Segments: $total_segments"
    echo "  Total Disconnects: $total_disconnects"
    echo "  Total Reconnects: $total_reconnects"
    echo "  Avg Segment Processing: ${avg_segment_time}µs"

    # Save summary
    cat << EOF > "$OUTPUT_DIR/${label}_summary.txt"
Branch: $label
Duration: ${DURATION}s
Device: $(adb shell getprop ro.product.model)
Android: $(adb shell getprop ro.build.version.release)
Timestamp: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

=== CPU Metrics ===
Average CPU: ${avg_cpu}%
Max CPU: ${max_cpu}%

=== Connection Stability ===
Total Segments: $total_segments
Total Disconnects: $total_disconnects
Total Reconnects: $total_reconnects
Disconnect Rate: $(echo "scale=2; $total_disconnects * 60 / $DURATION" | bc 2>/dev/null || echo "N/A")/min

=== Performance ===
Avg Segment Processing: ${avg_segment_time}µs
EOF
}

# Generate comparison report
generate_report() {
    log_info "Generating comparison report..."

    local old_summary="$OUTPUT_DIR/build_659_summary.txt"
    local new_summary="$OUTPUT_DIR/main_branch_summary.txt"
    local report="$OUTPUT_DIR/comparison_report.md"

    cat << 'EOF' > "$report"
# Disconnect Issue A/B Comparison Report

## Test Configuration
EOF

    echo "- **Device:** $(adb shell getprop ro.product.model)" >> "$report"
    echo "- **Android Version:** $(adb shell getprop ro.build.version.release)" >> "$report"
    echo "- **Duration:** ${DURATION}s per branch" >> "$report"
    echo "- **Date:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")" >> "$report"
    echo "" >> "$report"

    echo "## Results Summary" >> "$report"
    echo "" >> "$report"
    echo "| Metric | Build 659 | Main Branch | Delta |" >> "$report"
    echo "|--------|-----------|-------------|-------|" >> "$report"

    if [[ -f "$old_summary" ]] && [[ -f "$new_summary" ]]; then
        local old_cpu=$(grep "Average CPU" "$old_summary" | awk '{print $3}' | tr -d '%')
        local new_cpu=$(grep "Average CPU" "$new_summary" | awk '{print $3}' | tr -d '%')
        local old_disc=$(grep "Total Disconnects" "$old_summary" | awk '{print $3}')
        local new_disc=$(grep "Total Disconnects" "$new_summary" | awk '{print $3}')
        local old_seg=$(grep "Total Segments" "$old_summary" | awk '{print $3}')
        local new_seg=$(grep "Total Segments" "$new_summary" | awk '{print $3}')

        echo "| Avg CPU | ${old_cpu}% | ${new_cpu}% | $(echo "scale=1; $new_cpu - $old_cpu" | bc 2>/dev/null || echo "N/A")% |" >> "$report"
        echo "| Disconnects | $old_disc | $new_disc | $(echo "$new_disc - $old_disc" | bc 2>/dev/null || echo "N/A") |" >> "$report"
        echo "| Segments | $old_seg | $new_seg | $(echo "$new_seg - $old_seg" | bc 2>/dev/null || echo "N/A") |" >> "$report"
    fi

    echo "" >> "$report"
    echo "## Raw Data" >> "$report"
    echo "- Build 659 summary: \`$old_summary\`" >> "$report"
    echo "- Main branch summary: \`$new_summary\`" >> "$report"
    echo "- CPU samples: \`*_cpu_samples.csv\`" >> "$report"
    echo "- Event logs: \`*_events.log\`" >> "$report"

    log_success "Report saved to $report"
    cat "$report"
}

# Main execution
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║     A/B Disconnect Profiling: Build 659 vs Main Branch      ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  This script will:                                          ║"
    echo "║  1. Build & profile Build 659 (reported disconnect issues)  ║"
    echo "║  2. Build & profile Main branch (with fixes)                ║"
    echo "║  3. Generate comparison report                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    check_device

    # Save current branch
    local original_branch=$(git branch --show-current)
    log_info "Original branch: $original_branch"

    # Save profiling patch from current branch
    save_profiling_patch

    # ============ PROFILE BUILD 659 ============
    log_info "=========================================="
    log_info "PHASE 1: Profiling Build 659 ($COMMIT_OLD)"
    log_info "=========================================="

    # Checkout old commit, apply patch, build
    git stash push -m "profiling-temp" -- app/lib/providers/*.dart 2>/dev/null || true
    git checkout "$COMMIT_OLD" --quiet
    apply_profiling_patch || log_warn "Running without full profiling patch"
    build_apk "build_659"
    install_apk "build_659"
    launch_app

    echo ""
    log_warn ">>> Connect your Omi device and start a recording session <<<"
    log_warn ">>> Press ENTER when ready to begin profiling..."
    read -r

    profile_branch "build_659"

    # ============ PROFILE MAIN BRANCH ============
    log_info "=========================================="
    log_info "PHASE 2: Profiling Main Branch"
    log_info "=========================================="

    # Go back to profiling branch
    git checkout "$original_branch" --quiet
    git stash pop 2>/dev/null || true

    build_apk "main_branch"
    install_apk "main_branch"
    launch_app

    echo ""
    log_warn ">>> Connect your Omi device and start a recording session <<<"
    log_warn ">>> Press ENTER when ready to begin profiling..."
    read -r

    profile_branch "main_branch"

    # ============ GENERATE REPORT ============
    log_info "=========================================="
    log_info "PHASE 3: Generating Comparison Report"
    log_info "=========================================="

    generate_report

    log_success "A/B comparison complete! Results in $OUTPUT_DIR/"
}

# Run main if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
