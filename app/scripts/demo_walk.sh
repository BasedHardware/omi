#!/usr/bin/env bash
# Record a demo walk on one iOS simulator.
# Docs: app/e2e/SKILL.md, "Demo walk". The video is never committed.
#
#   app/scripts/demo_walk.sh --list
#   app/scripts/demo_walk.sh --walk ui-cleanup --out /tmp/omi-demo-walk.mp4
#   app/scripts/demo_walk.sh --walk ui-cleanup --device <UDID> --out /tmp/omi-demo-walk.mp4
#
# Add a page in app/integration_test/visual_audit/walks.dart (a DemoWalkStep whose id is a
# visual-audit scenario). This script generates the dev flavor files, boots one simulator,
# runs the walk, and records it with simctl. It does not set OMI_SKIP_BACKEND,
# OMI_PYTHON_API_URL, or OMI_DESKTOP_API_URL.
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="$(git -C "$app_dir" rev-parse --show-toplevel)"
walks_file="$app_dir/integration_test/visual_audit/walks.dart"

usage() { sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

walk='ui-cleanup'
device=''
out=''
hold=''
while (($#)); do
  case "$1" in
    --walk) walk="${2:?--walk needs a walk id}"; shift 2 ;;
    --device) device="${2:?--device needs a simulator UDID}"; shift 2 ;;
    --out) out="${2:?--out needs a file path}"; shift 2 ;;
    --hold-ms) hold="${2:?--hold-ms needs milliseconds}"; shift 2 ;;
    --list)
      echo "walks:"
      grep -E "id: '" "$walks_file" | sed -E "s/.*id: '([^']+)'.*/  \\1/"
      echo "ui-cleanup steps:"
      grep -E "DemoWalkStep\\('" "$walks_file" | sed -E "s/.*DemoWalkStep\\('([^']+)'.*/  \\1/"
      exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "$out" ]] || { usage >&2; exit 2; }
out="$(mkdir -p "$(dirname "$out")" && cd "$(dirname "$out")" && pwd)/$(basename "$out")"
case "$out" in
  *.mp4) ;;
  *) echo "--out must be an .mp4 file: $out" >&2; exit 2 ;;
esac
case "$out/" in
  "$repo_root"/*) echo "Output must be outside the repository (videos are never committed): $out" >&2; exit 2 ;;
esac
grep -q "id: '$walk'" "$walks_file" || { echo "Unknown walk: $walk (see --list)" >&2; exit 2; }

# Never point this build at a hosted API. Empty API_BASE_URL is loopback-legal for the hermetic check.
unset OMI_SKIP_BACKEND OMI_PYTHON_API_URL OMI_DESKTOP_API_URL OMI_APP_TEST_API_BASE_URL || true

prepare() {
  local missing=0
  for file in lib/firebase_options_dev.dart lib/firebase_options_prod.dart lib/env/dev_env.g.dart lib/env/prod_env.g.dart; do
    [[ -f "$app_dir/$file" ]] || missing=1
  done
  if [[ ! -f "$app_dir/.dev.env" ]]; then
    missing=1
  fi
  if [[ "$missing" -eq 0 ]]; then
    return
  fi
  echo "Preparing dev flavor files"
  (
    cd "$app_dir"
    mkdir -p android/app/src/dev/ android/app/src/prod/ ios/Config/Dev/ ios/Config/Prod/ ios/Runner/ macos/ macos/Config/Dev/ macos/Config/Prod
    cp lib/firebase_options_local.dart lib/firebase_options_dev.dart
    cp lib/firebase_options_local.dart lib/firebase_options_prod.dart
    cp setup/prebuilt/google-services-local.json android/app/src/dev/google-services.json
    cp setup/prebuilt/google-services-local.json android/app/src/prod/google-services.json
    cp setup/prebuilt/GoogleService-Info-Local.plist ios/Config/Dev/GoogleService-Info.plist
    cp setup/prebuilt/GoogleService-Info-Local.plist ios/Config/Prod/GoogleService-Info.plist
    cp setup/prebuilt/GoogleService-Info-Local.plist ios/Runner/GoogleService-Info.plist
    cp setup/prebuilt/GoogleService-Info-Local.plist macos/GoogleService-Info.plist
    cp setup/prebuilt/GoogleService-Info-Local.plist macos/Config/Dev/GoogleService-Info.plist
    cp setup/prebuilt/GoogleService-Info-Local.plist macos/Config/Prod/GoogleService-Info.plist
    printf 'API_BASE_URL=\nUSE_WEB_AUTH=true\nUSE_AUTH_CUSTOM_TOKEN=true\n' > .dev.env
    flutter pub get
    flutter pub run build_runner build --delete-conflicting-outputs
  )
}

choose_device() {
  python3 - "$device" <<'PY'
import json, subprocess, sys
want = sys.argv[1]
raw = subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"])
data = json.loads(raw)
booted = []
match = None
fallback = None
for runtime, devices in data.get("devices", {}).items():
    if "iOS" not in runtime:
        continue
    for device in devices:
        if not device.get("isAvailable"):
            continue
        if device.get("state") == "Booted":
            booted.append(device["udid"])
        if want and device["udid"] == want:
            match = device
        if not want and device.get("name") == "iPhone 17 Pro" and fallback is None:
            fallback = device
chosen = match if want else fallback
if chosen is None:
    sys.stderr.write("No matching iOS simulator. Pass --device UDID.\n")
    sys.exit(2)
others = [udid for udid in booted if udid != chosen["udid"]]
if others:
    sys.stderr.write("Another simulator is already booted (%s). Boot only one.\n" % ", ".join(others))
    sys.exit(2)
print("%s %s" % (chosen["udid"], chosen["state"]))
PY
}

prepare
bash "$app_dir/scripts/check_hermetic_test_env.sh" --app-dir "$app_dir"

read -r device state <<<"$(choose_device)"
echo "Simulator $device ($state)"
if [[ "$state" != "Booted" ]]; then
  xcrun simctl boot "$device"
  xcrun simctl bootstatus "$device" -b
fi

marker="$(mktemp "${TMPDIR:-/tmp}/omi-demo-walk-marker.XXXXXX")"
log="$(mktemp "${TMPDIR:-/tmp}/omi-demo-walk-log.XXXXXX")"
: >"$marker"
rec_pid=''
test_pid=''
cleanup() {
  local status=$?
  if [[ -n "$rec_pid" ]] && kill -0 "$rec_pid" 2>/dev/null; then
    kill -INT "$rec_pid" 2>/dev/null || true
    wait "$rec_pid" 2>/dev/null || true
  fi
  if [[ -n "$test_pid" ]] && kill -0 "$test_pid" 2>/dev/null; then
    kill -INT "$test_pid" 2>/dev/null || true
    wait "$test_pid" 2>/dev/null || true
  fi
  rm -f "$marker"
  if [[ "$status" -ne 0 ]]; then
    echo "Walk log: $log" >&2
  fi
}
trap cleanup EXIT

(
  cd "$app_dir"
  OMI_DEMO_WALK="$walk" \
  OMI_DEMO_WALK_MARKER="$marker" \
  ${hold:+OMI_DEMO_WALK_HOLD_MS="$hold"} \
    flutter test -d "$device" --flavor dev integration_test/visual_audit/demo_walk_test.dart --reporter expanded
) >"$log" 2>&1 &
test_pid=$!

# The walk runs inside the simulator. A host file path in OMI_DEMO_WALK_MARKER is not
# writable there, and the device isolate's stdout is not the host log. The host-visible
# signal is the test reporter line ("demo walk <id>"), which is printed when the test
# starts, before the first page's hold. A host-side run can still drop DEMO_WALK_READY
# into the marker file.
echo "Waiting for the walk to start (a cold iOS build can take a long time)"
ready=0
# 40 minutes. A first dev-flavor simulator build (pods + compile) often exceeds 10.
for _ in $(seq 1 4800); do
  if grep -q DEMO_WALK_READY "$marker" || grep -q "demo walk " "$log"; then
    ready=1
    break
  fi
  if ! kill -0 "$test_pid" 2>/dev/null; then
    echo "Walk exited before the first page. Log: $log" >&2
    tail -n 80 "$log" >&2 || true
    wait "$test_pid" || true
    exit 1
  fi
  sleep 0.5
done
if [[ "$ready" -ne 1 ]]; then
  echo "Timed out waiting for the walk to start. Log: $log" >&2
  tail -n 40 "$log" >&2 || true
  exit 1
fi
if ! kill -0 "$test_pid" 2>/dev/null; then
  echo "Walk finished before recording could start. Log: $log" >&2
  tail -n 40 "$log" >&2 || true
  exit 1
fi

echo "Recording $out"
xcrun simctl io "$device" recordVideo --codec h264 --force "$out" &
rec_pid=$!

# The test holds the first page for 3s after it is painted so this process can attach.
while kill -0 "$test_pid" 2>/dev/null; do
  if grep -q DEMO_WALK_DONE "$marker" || grep -q DEMO_WALK_DONE "$log"; then
    sleep 1
    break
  fi
  sleep 0.5
done
set +e
wait "$test_pid"
test_status=$?
set -e
test_pid=''

if [[ -n "$rec_pid" ]] && kill -0 "$rec_pid" 2>/dev/null; then
  kill -INT "$rec_pid" 2>/dev/null || true
  wait "$rec_pid" 2>/dev/null || true
fi
rec_pid=''

if [[ "$test_status" -ne 0 ]]; then
  echo "Walk failed (exit $test_status). Log: $log" >&2
  tail -n 80 "$log" >&2 || true
  exit "$test_status"
fi
if ! grep -q DEMO_WALK_DONE "$marker" && ! grep -q DEMO_WALK_DONE "$log" && ! grep -q "All tests passed" "$log"; then
  echo "Walk process ended without a passing result. Log: $log" >&2
  exit 1
fi
[[ -s "$out" ]] || { echo "Recording is empty: $out" >&2; exit 1; }
echo "Recorded $out"
echo "Log: $log"
