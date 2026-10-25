#!/usr/bin/env bash
# Heavy-account runner. iOS simulators support debug qualification ONLY.
# Run via: bin/omi-heavy run -- nice -n 19 bash app/tool/perf_sim_profile.sh ...
set -euo pipefail
cd "$(dirname "$0")/.."

RUNS=3
DEVICE=""
OUT_DIR=""
MODE=profile
PLATFORM=ios
TIMELINE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --runs) RUNS="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --out) OUT_DIR="$2"; shift 2 ;;
    --simulator-qualification) MODE=debug; shift ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --timeline) TIMELINE=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done
[[ "$RUNS" =~ ^[1-9][0-9]*$ ]] || { echo 'runs must be positive' >&2; exit 64; }
[[ -n "$DEVICE" ]] || { echo 'pass --device UDID (use a dedicated development device)' >&2; exit 64; }
[[ "$PLATFORM" == ios || "$PLATFORM" == android ]] || { echo 'platform must be ios or android' >&2; exit 64; }
[[ -n "$OUT_DIR" ]] || OUT_DIR="${TMPDIR:-/tmp}/omi-heavy-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_DIR"
OUT_DIR="$(realpath "$OUT_DIR")"
[[ -z "$(find "$OUT_DIR" -name 'receipt-*.json' -print -quit)" ]] || {
  echo 'output directory already contains receipts; choose a fresh directory' >&2; exit 64;
}

SIMULATOR=0
if [[ "$PLATFORM" == ios ]] && xcrun simctl getenv "$DEVICE" SIMULATOR_MODEL_IDENTIFIER >/dev/null 2>&1; then SIMULATOR=1; fi
if [[ "$PLATFORM" == android ]]; then
  [[ "$(adb -s "$DEVICE" get-state)" == device ]] || { echo 'Android device is not authorized/connected' >&2; exit 65; }
  [[ "$(adb -s "$DEVICE" shell getprop ro.kernel.qemu | tr -d '\r')" != 1 ]] || {
    echo 'Android acceptance requires a physical device' >&2; exit 65;
  }
fi
if [[ "$MODE" == profile && "$SIMULATOR" == 1 ]]; then
  echo 'Flutter forbids iOS simulator profile builds. Use a physical device for acceptance, or --simulator-qualification for debug diagnostics.' >&2
  exit 65
fi
if [[ "$MODE" == debug && "$SIMULATOR" != 1 ]]; then
  echo '--simulator-qualification requires an already booted iOS simulator' >&2; exit 65
fi

TARGET=integration_test/perf/heavy_profile_main.dart
DEFINES=(--dart-define=OMI_APP_PROFILE=local_dev)
if [[ "$TIMELINE" == 1 ]]; then DEFINES+=(--dart-define=PERF_HEAVY_TIMELINE=true); fi
BUILD_ARGS=(--"$MODE" --flavor dev --target "$TARGET")
if [[ "$SIMULATOR" == 1 ]]; then
  DEFINES+=(--dart-define=PERF_SIM_QUALIFICATION=true)
  BUILD_ARGS+=(--simulator --no-codesign)
  # Invocation-only overrides, including the unused watch byproduct. Never
  # change checked-in release/prod project settings for a local benchmark.
  printf '%s\n' 'ARCHS = arm64' 'EXCLUDED_ARCHS[sdk=iphonesimulator*] = i386 x86_64' \
    'CODE_SIGNING_ALLOWED = NO' 'CODE_SIGN_ENTITLEMENTS =' > "$OUT_DIR/simulator.xcconfig"
  export XCODE_XCCONFIG_FILE="$OUT_DIR/simulator.xcconfig"
fi

git rev-parse HEAD > "$OUT_DIR/source-sha.txt"
printf '%s\n' "$DEVICE" > "$OUT_DIR/device-id.txt"
printf '%s\n' "$PLATFORM" > "$OUT_DIR/platform.txt"
git diff HEAD --binary -- . > "$OUT_DIR/source.patch"
find integration_test/perf -name 'heavy_*.dart' -exec shasum -a 256 {} + > "$OUT_DIR/harness-sha256.txt"
shasum -a 256 test_driver/heavy_profile_driver.dart >> "$OUT_DIR/harness-sha256.txt"
flutter --version --machine > "$OUT_DIR/flutter-version.json"
OMI_APP_PROFILE=local_dev bash scripts/validate_mobile_build_config.sh --flavor dev --profile local_dev > "$OUT_DIR/config-validation.log" 2>&1
if [[ "$PLATFORM" == android ]]; then
  flutter build apk "${BUILD_ARGS[@]}" "${DEFINES[@]}" > "$OUT_DIR/build.log" 2>&1
  BINARY=build/app/outputs/flutter-apk/app-dev-profile.apk
else
  flutter build ios -d "$DEVICE" "${BUILD_ARGS[@]}" "${DEFINES[@]}" > "$OUT_DIR/build.log" 2>&1
fi
if [[ "$PLATFORM" == ios && "$SIMULATOR" == 1 ]]; then
  BINARY=build/ios/iphonesimulator/Runner.app
elif [[ "$PLATFORM" == ios ]]; then
  BINARY=build/ios/iphoneos/Runner.app
fi
[[ -e "$BINARY" ]] || { echo "missing $BINARY; see $OUT_DIR/build.log" >&2; exit 1; }
if [[ "$PLATFORM" == ios ]]; then
  BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$BINARY/Info.plist")"
  [[ "$BUNDLE_ID" == com.friend-app-with-wearable.ios12.development ]] || {
    echo 'Refusing to install an artifact outside the DEV bundle identity' >&2; exit 65;
  }
fi
# Reuse this exact binary for every run.
find "$BINARY" -type f -exec shasum -a 256 {} + | LC_ALL=C sort | shasum -a 256 > "$OUT_DIR/binary-sha256.txt"

if [[ "$PLATFORM" == ios && "$SIMULATOR" != 1 ]]; then
  # Update the exact DEV bundle in place; never uninstall or remove its data.
  xcrun devicectl device install app --device "$DEVICE" --timeout 90 "$BINARY" > "$OUT_DIR/install.log" 2>&1
fi
for ((run=1; run<=RUNS; run++)); do
  for attempt in 1 2 3; do
    ATTEMPT_DIR="$OUT_DIR/attempts/run-$run-try-$attempt"
    mkdir -p "$ATTEMPT_DIR"
    for identity in source-sha.txt binary-sha256.txt harness-sha256.txt flutter-version.json device-id.txt platform.txt; do
      cp "$OUT_DIR/$identity" "$ATTEMPT_DIR/$identity"
    done
    echo "heavy $MODE run $run/$RUNS attempt $attempt/3 on $DEVICE"
    if [[ "$PLATFORM" == ios && "$SIMULATOR" != 1 ]]; then
      xcrun devicectl device process launch --terminate-existing --device "$DEVICE" --timeout 20 \
        "$BUNDLE_ID" -- --start-paused > "$ATTEMPT_DIR/foreground.log" 2>&1
    fi
    if OMI_PERF_DEVICE_OUTPUT_DIR="$ATTEMPT_DIR" \
      OMI_PERF_RUN_NUMBER="$run" \
      OMI_PERF_TIMELINE="$TIMELINE" \
      OMI_PERF_SIMULATOR="$SIMULATOR" \
      python3 -I tool/perf_drive.py "$ATTEMPT_DIR/driver.log" \
      flutter drive --"$MODE" --flavor dev --no-pub --no-dds \
      --driver=test_driver/heavy_profile_driver.dart --target="$TARGET" \
      --use-application-binary="$BINARY" "${DEFINES[@]}" -d "$DEVICE"; then
      [[ -s "$ATTEMPT_DIR/integration_response_data.json" ]] || {
        echo "run $run produced no receipt" >&2; exit 1;
      }
      cp "$ATTEMPT_DIR/integration_response_data.json" "$OUT_DIR/receipt-$run.json"
      if [[ -f "$ATTEMPT_DIR/receipt-$run-timeline.json" ]]; then
        cp "$ATTEMPT_DIR/receipt-$run-timeline.json" "$OUT_DIR/receipt-$run-timeline.json"
      fi
      break
    fi
    tail -60 "$ATTEMPT_DIR/driver.log" >&2
    if [[ "$attempt" == 3 || ! -f "$ATTEMPT_DIR/measurement-rejected.json" ]]; then exit 1; fi
    echo "foreground/frame rejection preserved in $ATTEMPT_DIR; retrying this invalid measurement"
  done
  # CPU-table export belongs to the separate attribution run. Keep a fixed
  # between-run interval; never rerun valid slow frames to improve variance.
  if [[ "$run" -lt "$RUNS" ]]; then sleep 30; fi
done
python3 -I tool/perf_sim_report.py "$OUT_DIR" --expected-runs "$RUNS"
echo "receipts: $OUT_DIR"
