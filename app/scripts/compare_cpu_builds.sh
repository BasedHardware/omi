#!/usr/bin/env bash
# Compare CPU usage between two APK builds.
#
# Usage:
#   ./compare_cpu_builds.sh <apk1_path> <apk1_name> <apk2_path> <apk2_name> [-p <package>] [-s <device>] [-n <samples>] [-d <delay>]

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: compare_cpu_builds.sh <apk1_path> <apk1_name> <apk2_path> <apk2_name> [-p <package>] [-s <device>] [-n <samples>] [-d <delay>]
USAGE
}

PACKAGE="${PACKAGE_NAME:-${PACKAGE:-com.friend.ios.dev}}"
DEVICE="${DEVICE_ID:-}"
SAMPLES=15
DELAY=2

while getopts ":p:s:n:d:h" opt; do
  case "$opt" in
    p) PACKAGE="$OPTARG" ;;
    s) DEVICE="$OPTARG" ;;
    n) SAMPLES="$OPTARG" ;;
    d) DELAY="$OPTARG" ;;
    h) usage; exit 0 ;;
    \?) echo "Unknown option: -$OPTARG" >&2; usage; exit 2 ;;
    :) echo "Missing argument for -$OPTARG" >&2; usage; exit 2 ;;
  esac
done
shift $((OPTIND - 1))

if [ $# -lt 4 ]; then
  usage
  exit 1
fi

APK1_PATH=$1
APK1_NAME=$2
APK2_PATH=$3
APK2_NAME=$4

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEASURE_SCRIPT="$SCRIPT_DIR/measure_cpu_android.sh"

if [[ ! -x "$MEASURE_SCRIPT" ]]; then
  echo "Error: missing $MEASURE_SCRIPT" >&2
  exit 1
fi

if [[ -z "$DEVICE" ]]; then
  DEVICE=$(adb devices | awk 'NR>1 && $2=="device" {print $1; exit}')
fi

if [[ -z "$DEVICE" ]]; then
  echo "Error: no connected Android devices found." >&2
  exit 2
fi

if ! adb -s "$DEVICE" get-state >/dev/null 2>&1; then
  echo "Error: device '$DEVICE' not available." >&2
  exit 2
fi

run_measure() {
  local apk_path=$1
  local label=$2
  local out_file=$3

  echo "═══ Installing and testing: $label ═══"
  adb -s "$DEVICE" install -r -d "$apk_path" >/dev/null
  adb -s "$DEVICE" shell pm clear "$PACKAGE" >/dev/null 2>&1 || true
  echo "Open the app now, wait ~10s, then keep it foregrounded..."
  sleep 10

  local output
  output=$("$MEASURE_SCRIPT" -p "$PACKAGE" -s "$DEVICE" -n "$SAMPLES" -d "$DELAY" -o "$out_file")
  echo "$output"
  echo "$output" | sed -n 's/Median CPU: \([0-9.]*\)%.*/\1/p'
}

OUTPUT_DIR="/tmp/omi_cpu_profiling"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUTPUT_DIR"

CSV1="$OUTPUT_DIR/${APK1_NAME}_${TIMESTAMP}.csv"
CSV2="$OUTPUT_DIR/${APK2_NAME}_${TIMESTAMP}.csv"

MED1=$(run_measure "$APK1_PATH" "$APK1_NAME" "$CSV1")
MED2=$(run_measure "$APK2_PATH" "$APK2_NAME" "$CSV2")

if [[ -z "$MED1" || -z "$MED2" ]]; then
  echo "Error: failed to capture median CPU for one or both builds." >&2
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    COMPARISON RESULTS                        ║"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "║ %-25s │ %10s%% CPU (median)         ║\n" "$APK1_NAME" "$MED1"
printf "║ %-25s │ %10s%% CPU (median)         ║\n" "$APK2_NAME" "$MED2"
echo "╠══════════════════════════════════════════════════════════════╣"

diff=$(echo "$MED1 - $MED2" | bc)
if (( $(echo "$diff > 0" | bc -l) )); then
  printf "║ Difference: %s uses +%.1f%% more CPU            ║\n" "$APK1_NAME" "$diff"
else
  diff=$(echo "$diff * -1" | bc)
  printf "║ Difference: %s uses +%.1f%% more CPU            ║\n" "$APK2_NAME" "$diff"
fi

echo "╚══════════════════════════════════════════════════════════════╝"

echo ""
echo "CSV outputs:"
echo "- $CSV1"
echo "- $CSV2"
