#!/bin/bash
# Compare CPU Usage Between Two APK Builds
#
# Usage:
#   ./compare_cpu_builds.sh <apk1_path> <apk1_name> <apk2_path> <apk2_name>
#
# Example:
#   ./compare_cpu_builds.sh \
#     build/app/outputs/flutter-apk/app-dev-profile-WITH-SHIMMER.apk "with-shimmer" \
#     build/app/outputs/flutter-apk/app-dev-profile-NO-SHIMMER.apk "no-shimmer"
#
# Prerequisites:
#   - ADB installed and device connected
#   - Both APKs built in profile mode

set -e

if [ $# -lt 4 ]; then
    echo "Usage: $0 <apk1_path> <apk1_name> <apk2_path> <apk2_name>"
    exit 1
fi

APK1_PATH=$1
APK1_NAME=$2
APK2_PATH=$3
APK2_NAME=$4

DURATION=30
SAMPLES=$((DURATION / 2))
PACKAGE="com.friend.ios.dev"

measure_cpu() {
    local name=$1
    local cpu_values=()

    echo "Measuring $name for ${DURATION}s..."

    for i in $(seq 1 $SAMPLES); do
        CPU=$(adb shell "top -b -n 1 -d 1 | grep $PACKAGE" 2>/dev/null | head -1 | awk '{print $9}')
        if [ -n "$CPU" ]; then
            cpu_values+=("$CPU")
            printf "  Sample %2d: %s%%\n" "$i" "$CPU"
        fi
        sleep 2
    done

    # Calculate average
    if [ ${#cpu_values[@]} -gt 0 ]; then
        sum=0
        for val in "${cpu_values[@]}"; do
            val=$(echo "$val" | tr -cd '0-9.')
            [ -n "$val" ] && sum=$(echo "$sum + $val" | bc)
        done
        echo "scale=1; $sum / ${#cpu_values[@]}" | bc
    else
        echo "0"
    fi
}

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         CPU COMPARISON BETWEEN BUILDS                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check device
if ! adb devices | grep -q "device$"; then
    echo "ERROR: No Android device connected"
    exit 1
fi

# Test APK 1
echo "═══ Installing and testing: $APK1_NAME ═══"
adb install -r "$APK1_PATH"
echo "Waiting for app to start (10s)..."
sleep 10
AVG1=$(measure_cpu "$APK1_NAME")
echo ""

# Test APK 2
echo "═══ Installing and testing: $APK2_NAME ═══"
adb install -r "$APK2_PATH"
echo "Waiting for app to start (10s)..."
sleep 10
AVG2=$(measure_cpu "$APK2_NAME")
echo ""

# Results
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    COMPARISON RESULTS                        ║"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "║ %-25s │ %10s%% CPU                  ║\n" "$APK1_NAME" "$AVG1"
printf "║ %-25s │ %10s%% CPU                  ║\n" "$APK2_NAME" "$AVG2"
echo "╠══════════════════════════════════════════════════════════════╣"

DIFF=$(echo "$AVG1 - $AVG2" | bc)
if (( $(echo "$DIFF > 0" | bc -l) )); then
    printf "║ Difference: $APK1_NAME uses +%.1f%% more CPU              ║\n" "$DIFF"
else
    DIFF=$(echo "$DIFF * -1" | bc)
    printf "║ Difference: $APK2_NAME uses +%.1f%% more CPU              ║\n" "$DIFF"
fi
echo "╚══════════════════════════════════════════════════════════════╝"
