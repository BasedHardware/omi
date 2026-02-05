#!/usr/bin/env bash
set -euo pipefail

# Full automated Flutter Android profiling script
# - Builds profile APK
# - Starts screen recording (scrcpy)
# - Installs and launches app
# - Waits for UI state (via uiautomator)
# - Measures CPU
# - Stops recording

usage() {
  cat <<'USAGE'
Usage: profile_flutter_android.sh [options]

Options:
  -p, --package <name>    Android package name (default: com.friend.ios.dev)
  -f, --flavor <flavor>   Flutter build flavor (default: dev)
  -s, --session <name>    Session name for recording (default: profile_<timestamp>)
  -w, --wait-for <text>   UI text to wait for via Semantics label (default: device_state_Listening)
  -d, --delay <seconds>   Delay after UI state before measuring (default: 10)
  -n, --samples <count>   Number of CPU samples (default: 15)
  -i, --interval <secs>   Interval between samples (default: 2)
  -o, --output <dir>      Output directory for recordings (default: ~/Downloads)
  --no-build              Skip building APK (use existing build)
  --no-record             Skip screen recording
  -h, --help              Show this help message

Examples:
  # Full automated profiling with defaults
  ./profile_flutter_android.sh

  # Skip build, custom session name
  ./profile_flutter_android.sh --no-build -s "test_v2"

  # Custom wait condition
  ./profile_flutter_android.sh -w "device_state_Connected" -d 5
USAGE
}

# Defaults
PACKAGE="com.friend.ios.dev"
FLAVOR="dev"
SESSION=""
WAIT_FOR="device_state_Listening"
DELAY_AFTER_STATE=10
SAMPLES=15
INTERVAL=2
OUTPUT_DIR="$HOME/Downloads"
DO_BUILD=true
DO_RECORD=true

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--package) PACKAGE="$2"; shift 2 ;;
    -f|--flavor) FLAVOR="$2"; shift 2 ;;
    -s|--session) SESSION="$2"; shift 2 ;;
    -w|--wait-for) WAIT_FOR="$2"; shift 2 ;;
    -d|--delay) DELAY_AFTER_STATE="$2"; shift 2 ;;
    -n|--samples) SAMPLES="$2"; shift 2 ;;
    -i|--interval) INTERVAL="$2"; shift 2 ;;
    -o|--output) OUTPUT_DIR="$2"; shift 2 ;;
    --no-build) DO_BUILD=false; shift ;;
    --no-record) DO_RECORD=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

# Generate session ID if not provided
if [[ -z "$SESSION" ]]; then
  SESSION="profile_$(date +%Y%m%d_%H%M%S)"
fi

echo "=== Flutter Android Profiling ==="
echo "Package: $PACKAGE"
echo "Session: $SESSION"
echo "Wait for: $WAIT_FOR"
echo ""

# Check prerequisites
if ! command -v adb &>/dev/null; then
  echo "Error: adb not found in PATH" >&2
  exit 1
fi

DEVICE=$(adb devices | awk 'NR>1 && $2=="device" {print $1; exit}')
if [[ -z "$DEVICE" ]]; then
  echo "Error: No Android device connected" >&2
  exit 1
fi
echo "Device: $DEVICE"

# Find app directory (look for pubspec.yaml)
APP_DIR="."
if [[ -f "pubspec.yaml" ]]; then
  APP_DIR="."
elif [[ -f "app/pubspec.yaml" ]]; then
  APP_DIR="app"
elif [[ -f "../pubspec.yaml" ]]; then
  APP_DIR=".."
else
  echo "Error: Cannot find Flutter app directory (pubspec.yaml)" >&2
  exit 1
fi

# Step 1: Build APK
if [[ "$DO_BUILD" == true ]]; then
  echo ""
  echo "=== Building profile APK ==="
  pushd "$APP_DIR" > /dev/null
  flutter build apk --flavor "$FLAVOR" --profile
  popd > /dev/null
fi

APK_PATH="$APP_DIR/build/app/outputs/flutter-apk/app-${FLAVOR}-profile.apk"
if [[ ! -f "$APK_PATH" ]]; then
  echo "Error: APK not found at $APK_PATH" >&2
  exit 1
fi

# Step 2: Start screen recording
SCRCPY_PID=""
RECORDING_FILE=""
if [[ "$DO_RECORD" == true ]]; then
  if command -v scrcpy &>/dev/null; then
    echo ""
    echo "=== Starting screen recording ==="
    RECORDING_FILE="$OUTPUT_DIR/profiling_${SESSION}.mp4"
    scrcpy --no-audio -r "$RECORDING_FILE" &
    SCRCPY_PID=$!
    sleep 2
    echo "Recording to: $RECORDING_FILE (PID: $SCRCPY_PID)"
  else
    echo "Warning: scrcpy not found, skipping screen recording"
    DO_RECORD=false
  fi
fi

# Cleanup function
cleanup() {
  if [[ -n "$SCRCPY_PID" ]] && kill -0 "$SCRCPY_PID" 2>/dev/null; then
    echo ""
    echo "=== Stopping recording ==="
    kill "$SCRCPY_PID" 2>/dev/null || true
    wait "$SCRCPY_PID" 2>/dev/null || true
    echo "Recording saved to: $RECORDING_FILE"
  fi
}
trap cleanup EXIT

# Step 3: Install APK
echo ""
echo "=== Installing APK ==="
adb -s "$DEVICE" install -r "$APK_PATH"

# Step 4: Launch app
echo ""
echo "=== Launching app ==="
# Extract main activity from package
ACTIVITY=$(adb -s "$DEVICE" shell pm dump "$PACKAGE" | grep -A1 "android.intent.action.MAIN" | grep -oP '[\w.]+/[\w.]+' | head -1 || echo "")
if [[ -z "$ACTIVITY" ]]; then
  # Fallback: try common activity name
  ACTIVITY="$PACKAGE/.MainActivity"
fi
adb -s "$DEVICE" shell am start -n "$ACTIVITY" || adb -s "$DEVICE" shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1

# Step 5: Wait for UI state
echo ""
echo "=== Waiting for UI state: $WAIT_FOR ==="
FOUND=false
for i in {1..60}; do
  if adb -s "$DEVICE" shell uiautomator dump /sdcard/ui.xml 2>/dev/null && \
     adb -s "$DEVICE" shell cat /sdcard/ui.xml 2>/dev/null | grep -q "$WAIT_FOR"; then
    echo "Found '$WAIT_FOR' after $i seconds"
    FOUND=true
    break
  fi
  printf "."
  sleep 1
done
echo ""

if [[ "$FOUND" != true ]]; then
  echo "Warning: Timeout waiting for '$WAIT_FOR' - continuing anyway"
fi

# Step 6: Wait additional delay
echo "Waiting ${DELAY_AFTER_STATE}s for stabilization..."
sleep "$DELAY_AFTER_STATE"

# Step 7: Measure CPU
echo ""
echo "=== Measuring CPU ==="

# Use the measure script if available, otherwise inline
MEASURE_SCRIPT="$APP_DIR/scripts/measure_cpu_android.sh"
if [[ -f "$MEASURE_SCRIPT" ]]; then
  "$MEASURE_SCRIPT" -p "$PACKAGE" -s "$DEVICE" -n "$SAMPLES" -d "$INTERVAL"
else
  # Inline CPU measurement
  values=()
  echo "Sampling CPU for $PACKAGE ($SAMPLES samples, ${INTERVAL}s interval)..."

  for ((i=1; i<=SAMPLES; i++)); do
    line=$(adb -s "$DEVICE" shell "top -b -n 1 -d 1" | grep -m 1 "$PACKAGE" | head -1 || true)
    cpu=$(echo "$line" | awk '{for (j=1; j<=NF; j++) if ($j ~ /^[0-9.]+%$/) {gsub(/%/,"",$j); print $j; exit}}')

    if [[ -n "$cpu" ]]; then
      values+=("$cpu")
      echo "Sample $i: $cpu%"
    else
      echo "Sample $i: (not found)"
    fi

    if (( i < SAMPLES )); then
      sleep "$INTERVAL"
    fi
  done

  # Calculate median
  count=${#values[@]}
  if (( count > 0 )); then
    sorted=$(printf "%s\n" "${values[@]}" | sort -n)
    if (( count % 2 == 1 )); then
      median=$(printf "%s\n" "$sorted" | awk -v n="$count" 'NR==(n+1)/2 {print $1}')
    else
      median=$(printf "%s\n" "$sorted" | awk -v n="$count" 'NR==n/2 {a=$1} NR==n/2+1 {print (a+$1)/2}')
    fi
    echo "Median CPU: ${median}% (n=${count})"
  else
    echo "Error: No CPU samples collected"
  fi
fi

echo ""
echo "=== Profiling complete ==="
echo "Session: $SESSION"
if [[ -n "$RECORDING_FILE" ]] && [[ -f "$RECORDING_FILE" ]]; then
  echo "Recording: $RECORDING_FILE"
fi
