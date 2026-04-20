#!/usr/bin/env bash
#
# Run Omi app performance tests and generate reports.
#
# Usage:
#   ./run_performance_tests.sh                  # Run all perf tests
#   ./run_performance_tests.sh --duration 1h    # Extended run (for battery)
#   ./run_performance_tests.sh --report-only    # Just generate report from last run
#
# Prerequisites:
#   - Flutter SDK installed
#   - Device connected (adb devices / xcrun simctl list)
#   - App built in profile mode: flutter build apk --profile --flavor dev
#
# Outputs:
#   - app/perf_reports/perf_trace.json (Chrome-compatible trace)
#   - app/perf_reports/summary.json (machine-readable metrics)
#   - app/perf_reports/summary.txt (human-readable report)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
REPORT_DIR="$APP_DIR/perf_reports"
DURATION="5m"
REPORT_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --duration) DURATION="$2"; shift 2 ;;
        --report-only) REPORT_ONLY=true; shift ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

mkdir -p "$REPORT_DIR"

echo "╔══════════════════════════════════════════════╗"
echo "║  Omi Performance Test Suite                 ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Duration:    $DURATION"
echo "Reports:     $REPORT_DIR"
echo ""

if [[ "$REPORT_ONLY" == true ]]; then
    echo "Generating report from existing data..."
else
    echo "═══ Phase 1: Integration Performance Tests ═══"
    echo ""

    # Run Flutter integration tests in profile mode with tracing
    cd "$APP_DIR"
    flutter test integration_test/performance_suite_test.dart \
        --profile \
        --trace-to-file="$REPORT_DIR/perf_trace.json" \
        2>&1 | tee "$REPORT_DIR/test_output.log" || true

    echo ""
    echo "═══ Phase 2: Memory Leak Detection ═══"
    echo ""

    # Run leak tracker tests if available
    if [[ -f "integration_test/memory_leak_test.dart" ]]; then
        flutter test integration_test/memory_leak_test.dart \
            --profile \
            2>&1 | tee -a "$REPORT_DIR/test_output.log" || true
    fi

    echo ""
    echo "═══ Phase 3: Extended Battery/CPU Monitoring ═══"
    echo ""

    # If duration > 5m, run continuous monitoring
    if [[ "$DURATION" != "5m" ]]; then
        echo "Running extended monitoring for $DURATION..."
        echo "Collecting: CPU %, memory RSS, battery level"

        END_TIME=$((SECONDS + $(echo "$DURATION" | sed 's/h/*3600/;s/m/*60/;s/s//' | bc)))

        while [[ $SECONDS -lt $END_TIME ]]; do
            # Android: collect metrics via adb
            if adb devices 2>/dev/null | grep -q "device$"; then
                TIMESTAMP=$(date +%s)
                MEM=$(adb shell dumpsys meminfo com.friend.ios.dev 2>/dev/null | grep "TOTAL PSS" | awk '{print $3}')
                CPU=$(adb shell top -n 1 -b 2>/dev/null | grep "com.friend.ios.dev" | awk '{print $9}')
                BAT=$(adb shell dumpsys battery 2>/dev/null | grep "level:" | awk '{print $2}')
                echo "$TIMESTAMP,$MEM,$CPU,$BAT" >> "$REPORT_DIR/extended_metrics.csv"
            fi
            sleep 30
        done
    fi
fi

echo ""
echo "═══ Generating Summary Report ═══"
echo ""

# Generate human-readable summary
{
    echo "Omi Performance Test Report"
    echo "Generated: $(date)"
    echo "Platform: $(uname -s) $(uname -m)"
    echo ""
    echo "─── Results ───"
    echo ""

    if [[ -f "$REPORT_DIR/test_output.log" ]]; then
        grep -E "^(✓|✗|All tests|Test|PASS|FAIL)" "$REPORT_DIR/test_output.log" 2>/dev/null || echo "(see test_output.log)"
    fi

    echo ""
    echo "─── Files ───"
    ls -la "$REPORT_DIR"/ 2>/dev/null
    echo ""
    echo "─── Next Steps ───"
    echo "• Open perf_trace.json in chrome://tracing for frame analysis"
    echo "• Check extended_metrics.csv for battery/memory trends over time"
    echo "• Look for memory leaks in test_output.log (leak_tracker warnings)"
} > "$REPORT_DIR/summary.txt"

cat "$REPORT_DIR/summary.txt"
echo ""
echo "✅ Reports saved to: $REPORT_DIR/"
