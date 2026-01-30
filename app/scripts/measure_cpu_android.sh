#!/usr/bin/env bash
# Android CPU Measurement Script for Omi App
#
# Usage:
#   ./measure_cpu_android.sh -p <package> [-s <device>] [-n <samples>] [-d <delay>] [-o <csv>]
#
# Legacy usage (kept for backward compatibility):
#   ./measure_cpu_android.sh [duration_seconds] [output_name]
#
# Examples:
#   ./measure_cpu_android.sh -p com.friend.ios.dev -n 15 -d 2 -o /tmp/omi_cpu.csv
#   ./measure_cpu_android.sh 60 "baseline"

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: measure_cpu_android.sh -p <package> [-s <device>] [-n <samples>] [-d <delay>] [-o <csv>]

Options:
  -p  Android package name (default: env PACKAGE or com.friend.ios.dev)
  -s  Device ID (default: first connected device)
  -n  Number of samples (default: 15)
  -d  Delay between samples in seconds (default: 2)
  -o  Write CSV output (sample,cpu) to this file
USAGE
}

PACKAGE="${PACKAGE_NAME:-${PACKAGE:-}}"
PACKAGE_SET=false
DEVICE="${DEVICE_ID:-}"
SAMPLES=15
DELAY=2
OUTFILE=""
LEGACY_MODE=false

while getopts ":p:s:n:d:o:h" opt; do
  case "$opt" in
    p) PACKAGE="$OPTARG"; PACKAGE_SET=true ;;
    s) DEVICE="$OPTARG" ;;
    n) SAMPLES="$OPTARG" ;;
    d) DELAY="$OPTARG" ;;
    o) OUTFILE="$OPTARG" ;;
    h) usage; exit 0 ;;
    \?) echo "Unknown option: -$OPTARG" >&2; usage; exit 2 ;;
    :) echo "Missing argument for -$OPTARG" >&2; usage; exit 2 ;;
  esac
done

shift $((OPTIND - 1))

if ! $PACKAGE_SET && [[ $# -le 2 ]]; then
  # Legacy positional args: duration_seconds output_name
  LEGACY_MODE=true
  DURATION=${1:-60}
  OUTPUT_NAME=${2:-"measurement"}

  if ! [[ "$DURATION" =~ ^[0-9]+$ ]]; then
    echo "Error: invalid duration '$DURATION'" >&2
    usage
    exit 2
  fi

  SAMPLES=$((DURATION / 2))
  if (( SAMPLES < 1 )); then
    SAMPLES=1
  fi

  if [[ -z "$OUTFILE" ]]; then
    OUTPUT_DIR="/tmp/omi_cpu_profiling"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    mkdir -p "$OUTPUT_DIR"
    OUTFILE="$OUTPUT_DIR/${OUTPUT_NAME}_${TIMESTAMP}.csv"
  fi
elif [[ $# -gt 0 ]]; then
  echo "Error: unexpected extra arguments: $*" >&2
  usage
  exit 2
fi

if [[ -z "$PACKAGE" ]]; then
  PACKAGE="com.friend.ios.dev"
  echo "Warning: no package provided; defaulting to $PACKAGE" >&2
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

# Use standard top output without -o flag for consistent CPU% parsing
TOP_ARGS="-b -n 1 -d 1"

values=()

if [[ -n "$OUTFILE" ]]; then
  mkdir -p "$(dirname "$OUTFILE")"
  echo "sample,cpu" > "$OUTFILE"
fi

echo "Sampling CPU for $PACKAGE on $DEVICE ($SAMPLES samples, ${DELAY}s delay)..."

for ((i=1; i<=SAMPLES; i++)); do
  line=$(adb -s "$DEVICE" shell "top $TOP_ARGS" | grep -m 1 "$PACKAGE" | head -1 || true)
  # Try format with % suffix first, then fall back to column 9 (standard top format)
  cpu=$(echo "$line" | awk '{for (i=1; i<=NF; i++) if ($i ~ /^[0-9.]+%$/) {gsub(/%/,"",$i); print $i; exit}}')
  if [[ -z "$cpu" ]]; then
    # Fallback: extract column 9 which is CPU% in standard Android top output
    cpu=$(echo "$line" | awk '{print $9}' | grep -E '^[0-9.]+$' || true)
  fi

  if [[ -z "$cpu" ]]; then
    echo "Sample $i: missing (package not found or CPU column not parsed)" >&2
  else
    values+=("$cpu")
    echo "Sample $i: $cpu%"
    if [[ -n "$OUTFILE" ]]; then
      echo "$i,$cpu" >> "$OUTFILE"
    fi
  fi

  if (( i < SAMPLES )); then
    sleep "$DELAY"
  fi
done

count=${#values[@]}
if (( count == 0 )); then
  echo "Error: no CPU samples collected." >&2
  exit 1
fi

sorted=$(printf "%s\n" "${values[@]}" | sort -n)

if (( count % 2 == 1 )); then
  median=$(printf "%s\n" "$sorted" | awk -v n="$count" 'NR==(n+1)/2 {print $1}')
else
  median=$(printf "%s\n" "$sorted" | awk -v n="$count" 'NR==n/2 {a=$1} NR==n/2+1 {print (a+$1)/2}')
fi

echo "Median CPU: ${median}% (n=${count})"

if [[ -n "$OUTFILE" ]]; then
  echo "Wrote CSV to $OUTFILE"
fi
