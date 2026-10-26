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
VIRTUAL=0
RUNTIME_BUILD=""
WARMUP_RUNS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --runs) RUNS="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --out) OUT_DIR="$2"; shift 2 ;;
    --simulator-qualification) MODE=debug; VIRTUAL=1; shift ;;
    --emulator-qualification) VIRTUAL=1; shift ;;
    --runtime-build) RUNTIME_BUILD="$2"; shift 2 ;;
    --warmup-runs) WARMUP_RUNS="$2"; shift 2 ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --timeline) TIMELINE=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done
[[ "$RUNS" =~ ^[1-9][0-9]*$ ]] || { echo 'runs must be positive' >&2; exit 64; }
[[ "$WARMUP_RUNS" =~ ^[0-3]$ ]] || { echo 'warmup-runs must be a single digit 0..3' >&2; exit 64; }
if [[ "$VIRTUAL" == 1 && "$WARMUP_RUNS" -lt 1 ]]; then
  echo 'virtual qualification requires at least one retained warmup launch' >&2; exit 64
fi
if [[ "$VIRTUAL" == 0 && ( "$WARMUP_RUNS" != 0 || -n "$RUNTIME_BUILD" ) ]]; then
  echo 'warmup/runtime options require explicit virtual qualification' >&2; exit 64
fi
[[ -n "$DEVICE" ]] || { echo 'pass --device UDID (use a dedicated development device)' >&2; exit 64; }
[[ "$PLATFORM" == ios || "$PLATFORM" == android ]] || { echo 'platform must be ios or android' >&2; exit 64; }
if [[ "$VIRTUAL" == 1 && "$PLATFORM" == android && ! "$DEVICE" =~ ^emulator-[0-9]+$ ]]; then
  echo 'virtual Android target must be an explicit emulator serial' >&2; exit 65
fi
[[ -n "$OUT_DIR" ]] || OUT_DIR="${TMPDIR:-/tmp}/omi-heavy-$(date -u +%Y%m%dT%H%M%SZ)"
if [[ "$VIRTUAL" == 1 && -d "$OUT_DIR" && -n "$(find "$OUT_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo 'virtual output directory must be new or empty; retain failed batches separately' >&2; exit 64
fi
mkdir -p "$OUT_DIR"
OUT_DIR="$(realpath "$OUT_DIR")"
[[ -z "$(find "$OUT_DIR" -name 'receipt-*.json' -print -quit)" ]] || {
  echo 'output directory already contains receipts; choose a fresh directory' >&2; exit 64;
}

SIMULATOR=0
if [[ "$PLATFORM" == ios ]] && xcrun simctl getenv "$DEVICE" SIMULATOR_MODEL_IDENTIFIER >/dev/null 2>&1; then SIMULATOR=1; fi
if [[ "$PLATFORM" == android ]]; then
  if [[ "$VIRTUAL" == 1 && "$MODE" != profile ]]; then
    echo 'Android emulator qualification requires profile mode' >&2; exit 64
  fi
  [[ "$(adb -s "$DEVICE" get-state)" == device ]] || { echo 'Android device is not authorized/connected' >&2; exit 65; }
  if [[ "$VIRTUAL" == 0 ]]; then
    [[ "$(adb -s "$DEVICE" shell getprop ro.kernel.qemu | tr -d '\r')" != 1 ]] || {
      echo 'Android acceptance requires a physical device; opt into --emulator-qualification' >&2; exit 65;
    }
  fi
fi
if [[ "$VIRTUAL" == 1 ]]; then
  python3 -I tool/perf/virtual_admission.py --platform "$PLATFORM" --device "$DEVICE" \
    --runtime-build "$RUNTIME_BUILD" --out "$OUT_DIR/virtual-runtime.json"
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
if [[ "$VIRTUAL" == 1 ]]; then DEFINES+=(--dart-define=PERF_VIRTUAL_QUALIFICATION=true); fi
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
find integration_test/perf -name 'heavy_*.dart' -exec shasum -a 256 {} + > "$OUT_DIR/protocol-files.raw"
shasum -a 256 integration_test/perf/production_shell.dart test_driver/heavy_profile_driver.dart \
  tool/perf_sim_profile.sh tool/perf_sim_report.py tool/perf_drive.py tool/perf_device_run.sh \
  tool/perf/device_run.py tool/perf/compare.py >> "$OUT_DIR/protocol-files.raw"
shasum -a 256 tool/perf/device_admission.py >> "$OUT_DIR/protocol-files.raw"
shasum -a 256 tool/perf/virtual_admission.py >> "$OUT_DIR/protocol-files.raw"
shasum -a 256 tool/perf/host_load.py >> "$OUT_DIR/protocol-files.raw"
shasum -a 256 tool/perf/android_manifest.py android/app/build.gradle \
  android/app/src/heavyPerf/AndroidManifest.xml >> "$OUT_DIR/protocol-files.raw"
LC_ALL=C sort "$OUT_DIR/protocol-files.raw" > "$OUT_DIR/harness-sha256.txt"
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
if [[ "$PLATFORM" == android ]]; then
  python3 -I tool/perf/android_manifest.py "$BINARY" --out "$OUT_DIR/native-harness.json"
fi
if [[ "$PLATFORM" == ios ]]; then
  BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$BINARY/Info.plist")"
  [[ "$BUNDLE_ID" == com.friend-app-with-wearable.ios12.development ]] || {
    echo 'Refusing to install an artifact outside the DEV bundle identity' >&2; exit 65;
  }
fi
# Reuse this exact binary for every run.
find "$BINARY" -type f -exec shasum -a 256 {} + | LC_ALL=C sort | shasum -a 256 > "$OUT_DIR/binary-sha256.txt"

if [[ "$PLATFORM" == ios && "$SIMULATOR" != 1 ]]; then
  python3 -I tool/perf/device_admission.py --device "$DEVICE" --out "$OUT_DIR/admission-before-install.json"
  # Update the exact DEV bundle in place; never uninstall or remove its data.
  xcrun devicectl device install app --device "$DEVICE" --timeout 90 "$BINARY" > "$OUT_DIR/install.log" 2>&1
  CANARY_NAME="omi-heavy-preserve-$(uuidgen).txt"
  printf '%s\n' "$CANARY_NAME" > "$OUT_DIR/preservation-canary-name.txt"
  printf '%s\n' 'Synthetic heavy-profile sandbox preservation canary.' > "$OUT_DIR/preservation-canary.txt"
  xcrun devicectl device copy to --device "$DEVICE" --source "$OUT_DIR/preservation-canary.txt" \
    --domain-type appDataContainer --domain-identifier "$BUNDLE_ID" \
    --destination "Documents/$CANARY_NAME" --timeout 20 > "$OUT_DIR/canary-create.log" 2>&1
fi
printf '{"warmup_runs":%s,"measured_runs":%s,"outlier_policy":"retain-all","host_load_policy":"load1-per-logical-cpu<=1/v1"}\n' "$WARMUP_RUNS" "$RUNS" > "$OUT_DIR/launch-protocol.json"
for ((launch=1; launch<=RUNS+WARMUP_RUNS; launch++)); do
  run=$((launch-WARMUP_RUNS))
  PREFIX=receipt
  if [[ "$run" -le 0 ]]; then PREFIX=warmup; run="$launch"; fi
  for attempt in 1 2 3; do
    ATTEMPT_DIR="$OUT_DIR/attempts/$PREFIX-$run-try-$attempt"
    mkdir -p "$ATTEMPT_DIR"
    for identity in source-sha.txt binary-sha256.txt harness-sha256.txt flutter-version.json device-id.txt platform.txt; do
      cp "$OUT_DIR/$identity" "$ATTEMPT_DIR/$identity"
    done
    if [[ "$PLATFORM" == android ]]; then cp "$OUT_DIR/native-harness.json" "$ATTEMPT_DIR/native-harness.json"; fi
    echo "heavy $MODE $PREFIX $run attempt $attempt/3 on $DEVICE"
    if [[ "$VIRTUAL" == 1 ]]; then
      python3 -I tool/perf/virtual_admission.py --platform "$PLATFORM" --device "$DEVICE" \
        --runtime-build "$RUNTIME_BUILD" --out "$ATTEMPT_DIR/virtual-runtime.json" \
        --host-out "$ATTEMPT_DIR/host-state.json"
      cmp "$OUT_DIR/virtual-runtime.json" "$ATTEMPT_DIR/virtual-runtime.json"
      cp "$OUT_DIR/launch-protocol.json" "$ATTEMPT_DIR/launch-protocol.json"
    elif [[ "$SIMULATOR" != 1 ]]; then
      python3 -I tool/perf/device_admission.py --platform "$PLATFORM" --device "$DEVICE" \
        --out "$ATTEMPT_DIR/admission-before-launch.json"
    fi
    DRIVE_RESULT=0
    HOST_GUARD=()
    if [[ "$VIRTUAL" == 1 ]]; then
      HOST_GUARD=(python3 -I tool/perf/host_load.py --out "$ATTEMPT_DIR/host-load.json" --)
    fi
    OMI_PERF_DEVICE_OUTPUT_DIR="$ATTEMPT_DIR" \
      OMI_PERF_RUN_NUMBER="$run" \
      OMI_PERF_TIMELINE="$TIMELINE" \
      OMI_PERF_SIMULATOR="$SIMULATOR" \
      OMI_PERF_VIRTUAL="$VIRTUAL" \
      "${HOST_GUARD[@]}" python3 -I tool/perf_drive.py "$ATTEMPT_DIR/driver.log" \
      flutter drive --"$MODE" --flavor dev --no-pub --no-dds --keep-app-running --no-publish-port \
      --driver=test_driver/heavy_profile_driver.dart --target="$TARGET" \
      --use-application-binary="$BINARY" "${DEFINES[@]}" -d "$DEVICE" || DRIVE_RESULT=$?
    if [[ "$VIRTUAL" == 1 ]]; then
      cp "$ATTEMPT_DIR/host-load.json" "$OUT_DIR/$PREFIX-$run-host-load.json"
      # An otherwise completed slow/overloaded launch must never be retried.
      if [[ "$DRIVE_RESULT" == 65 ]]; then exit 65; fi
    fi
    if [[ "$PLATFORM" == ios && "$SIMULATOR" != 1 ]]; then
      xcrun devicectl device copy from --device "$DEVICE" --source "Documents/$CANARY_NAME" \
        --domain-type appDataContainer --domain-identifier "$BUNDLE_ID" \
        --destination "$ATTEMPT_DIR/preserved-canary.txt" --timeout 20 > "$ATTEMPT_DIR/canary-check.log" 2>&1
      cmp "$OUT_DIR/preservation-canary.txt" "$ATTEMPT_DIR/preserved-canary.txt" || {
        echo 'DEV sandbox preservation failed; stopping without retry' >&2; exit 1;
      }
      printf '{"verified":true,"bundle_id":"%s"}\n' "$BUNDLE_ID" > "$ATTEMPT_DIR/preservation.json"
    fi
    if [[ "$DRIVE_RESULT" == 0 ]]; then
      [[ -s "$ATTEMPT_DIR/integration_response_data.json" ]] || {
        echo "run $run produced no receipt" >&2; exit 1;
      }
      if [[ "$PLATFORM" == ios && "$SIMULATOR" != 1 ]]; then
        cp "$ATTEMPT_DIR/preservation.json" "$OUT_DIR/receipt-$run-preservation.json"
      fi
      cp "$ATTEMPT_DIR/integration_response_data.json" "$OUT_DIR/$PREFIX-$run.json"
      if [[ -f "$ATTEMPT_DIR/receipt-$run-timeline.json" ]]; then
        cp "$ATTEMPT_DIR/receipt-$run-timeline.json" "$OUT_DIR/$PREFIX-$run-timeline.json"
      fi
      break
    fi
    tail -60 "$ATTEMPT_DIR/driver.log" >&2
    if [[ "$attempt" == 3 || ! -f "$ATTEMPT_DIR/measurement-rejected.json" ]]; then exit 1; fi
    echo "foreground/frame rejection preserved in $ATTEMPT_DIR; retrying this invalid measurement"
  done
  # CPU-table export belongs to the separate attribution run. Keep a fixed
  # between-run interval; never rerun valid slow frames to improve variance.
  if [[ "$launch" -lt "$((RUNS+WARMUP_RUNS))" ]]; then sleep 30; fi
done
python3 -I tool/perf_sim_report.py "$OUT_DIR" --expected-runs "$RUNS"
echo "receipts: $OUT_DIR"
