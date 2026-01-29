#!/bin/bash
# Android CPU Measurement Script for Omi App
#
# Usage:
#   ./measure_cpu_android.sh [duration_seconds] [output_name]
#
# Examples:
#   ./measure_cpu_android.sh              # 60 seconds, default name
#   ./measure_cpu_android.sh 30           # 30 seconds
#   ./measure_cpu_android.sh 60 "shimmer" # 60 seconds, named "shimmer"
#
# Prerequisites:
#   - ADB installed and device connected
#   - App running in profile mode: flutter run --profile --flavor dev

set -e

DURATION=${1:-60}
OUTPUT_NAME=${2:-"measurement"}
SAMPLES=$((DURATION / 2))
PACKAGE="com.friend.ios.dev"
OUTPUT_DIR="/tmp/omi_cpu_profiling"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/${OUTPUT_NAME}_${TIMESTAMP}.txt"

mkdir -p "$OUTPUT_DIR"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         OMI ANDROID CPU MEASUREMENT                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Duration: ${DURATION}s (${SAMPLES} samples)"
echo "Package: $PACKAGE"
echo "Output: $OUTPUT_FILE"
echo ""

# Check device connection
if ! adb devices | grep -q "device$"; then
    echo "ERROR: No Android device connected"
    echo "Connect device and enable USB debugging"
    exit 1
fi

# Check if app is running
if ! adb shell "ps -A | grep $PACKAGE" > /dev/null 2>&1; then
    echo "ERROR: App not running"
    echo "Start the app with: flutter run --profile --flavor dev"
    exit 1
fi

echo "App found. Starting measurement..."
echo ""
echo "Timestamp: $(date)" > "$OUTPUT_FILE"
echo "Duration: ${DURATION}s" >> "$OUTPUT_FILE"
echo "Samples: ${SAMPLES}" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "CPU_PERCENT" >> "$OUTPUT_FILE"

cpu_values=()

for i in $(seq 1 $SAMPLES); do
    # Use top for accurate CPU measurement
    CPU=$(adb shell "top -b -n 1 -d 1 | grep $PACKAGE" 2>/dev/null | head -1 | awk '{print $9}')

    if [ -n "$CPU" ]; then
        echo "$CPU" >> "$OUTPUT_FILE"
        cpu_values+=("$CPU")
        printf "Sample %2d/%d: %s%%\n" "$i" "$SAMPLES" "$CPU"
    else
        echo "0" >> "$OUTPUT_FILE"
        cpu_values+=("0")
        printf "Sample %2d/%d: app not in top CPU\n" "$i" "$SAMPLES"
    fi

    sleep 2
done

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    RESULTS                                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# Calculate statistics
if [ ${#cpu_values[@]} -gt 0 ]; then
    sum=0
    min=${cpu_values[0]}
    max=${cpu_values[0]}

    for val in "${cpu_values[@]}"; do
        # Remove any non-numeric characters
        val=$(echo "$val" | tr -cd '0-9.')
        if [ -n "$val" ]; then
            sum=$(echo "$sum + $val" | bc)
            if (( $(echo "$val < $min" | bc -l) )); then min=$val; fi
            if (( $(echo "$val > $max" | bc -l) )); then max=$val; fi
        fi
    done

    avg=$(echo "scale=1; $sum / ${#cpu_values[@]}" | bc)

    echo ""
    echo "Samples: ${#cpu_values[@]}"
    echo "Average CPU: ${avg}%"
    echo "Min CPU: ${min}%"
    echo "Max CPU: ${max}%"
    echo ""
    echo "" >> "$OUTPUT_FILE"
    echo "SUMMARY" >> "$OUTPUT_FILE"
    echo "Average: ${avg}%" >> "$OUTPUT_FILE"
    echo "Min: ${min}%" >> "$OUTPUT_FILE"
    echo "Max: ${max}%" >> "$OUTPUT_FILE"
fi

echo "Results saved to: $OUTPUT_FILE"
