#!/usr/bin/env bash
#
# Behavioral tests for select_ios_device() in app/setup.sh.
#
# Regression covered: run_build_ios() passed no `-d` to `flutter run`, so
# Flutter picked a destination itself. On a machine with no iOS simulator
# runtime installed and only a wirelessly-paired phone visible, it silently
# built for macOS desktop instead and failed with an error about a platform
# the developer never asked for, several minutes into pod install/build_runner.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_SH="${SCRIPT_DIR}/../../setup.sh"

if [[ ! -f "$SETUP_SH" ]]; then
  echo "FAIL: cannot find setup.sh at $SETUP_SH" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "skip - select_ios_device tests need jq, not available on this host"
  exit 0
fi

failures=0
pass() { echo "  ok   - $1"; }
fail() { echo "  FAIL - $1" >&2; failures=$((failures + 1)); }

HARNESS="$(mktemp -t omi_ios_device_XXXXXX)"
trap 'rm -f "$HARNESS"' EXIT

extract_function() {
  awk -v fn="function $1()" '
    index($0, fn) == 1 { capture = 1 }
    capture { print }
    capture && $0 == "}" { exit }
  ' "$SETUP_SH"
}

{
  echo "set -uo pipefail"
  extract_function select_ios_device
} > "$HARNESS"

PHYSICAL_DEVICE_HARNESS="$(mktemp -t omi_ios_physical_XXXXXX)"
trap 'rm -f "$HARNESS" "$PHYSICAL_DEVICE_HARNESS"' EXIT
{
  echo "set -uo pipefail"
  extract_function _ios_device_is_physical
} > "$PHYSICAL_DEVICE_HARNESS"

if ! bash -n "$PHYSICAL_DEVICE_HARNESS"; then
  echo "FAIL: extracted _ios_device_is_physical harness is not valid bash" >&2
  exit 1
fi

if ! bash -n "$HARNESS"; then
  echo "FAIL: extracted harness is not valid bash" >&2
  exit 1
fi

# Stubs `flutter devices --machine` to return the given raw JSON array, plus
# real jq/coreutils so the extracted function actually runs.
stub_devices() {
  local root="$1" devices_json="$2"
  mkdir -p "$root/bin"
  for real in bash sort grep awk printf head cat jq; do
    ln -sf "$(command -v "$real")" "$root/bin/$real"
  done
  cat > "$root/bin/flutter" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "devices" ]]; then
  cat <<'JSON'
${devices_json}
JSON
  exit 0
fi
exit 1
EOF
  chmod +x "$root/bin/flutter"
}

run_selection() {
  local root="$1"; shift
  PATH="$root/bin" bash -c "source '$HARNESS'; select_ios_device" "$@"
}

echo "select_ios_device:"

# 1. Exactly one iOS destination: return it directly, no prompt.
root=$(mktemp -d -t omi_ios_dev_one_XXXXXX)
stub_devices "$root" '[
  {"name":"iPhone 17 Pro","id":"SIM-ABC-123","isSupported":true,"targetPlatform":"ios","emulator":true},
  {"name":"macOS","id":"macos","isSupported":true,"targetPlatform":"darwin","emulator":false}
]'
got=$(run_selection "$root" 2>/dev/null)
rm -rf "$root"
if [[ "$got" == "SIM-ABC-123" ]]; then
  pass "returns the single iOS device's id, ignoring the non-iOS macOS entry"
else
  fail "expected 'SIM-ABC-123', got '${got}'"
fi

# 2. No iOS destination (only macOS): fail with a clear message, not a
#    silent fallback to whatever flutter run would pick on its own.
root=$(mktemp -d -t omi_ios_dev_none_XXXXXX)
stub_devices "$root" '[
  {"name":"macOS","id":"macos","isSupported":true,"targetPlatform":"darwin","emulator":false}
]'
out=$(run_selection "$root" 2>&1); rc=$?
rm -rf "$root"
if [[ "$rc" -ne 0 ]] && [[ "$out" == *"No iOS device or simulator found"* ]]; then
  pass "fails with a named error instead of silently picking macOS (the regression)"
else
  fail "expected a named no-iOS-device failure, got (rc=$rc): $out"
fi

# 3. Multiple iOS destinations, no TTY attached: fail fast rather than block
#    on read, same reasoning as detect_apple_team_id's prompt.
root=$(mktemp -d -t omi_ios_dev_multi_XXXXXX)
stub_devices "$root" '[
  {"name":"Revtim'"'"'s iPhone","id":"PHYS-1","isSupported":true,"targetPlatform":"ios","emulator":false},
  {"name":"iPhone 17 Pro","id":"SIM-2","isSupported":true,"targetPlatform":"ios","emulator":true}
]'
rc=0
run_selection "$root" </dev/null >/dev/null 2>&1 || rc=$?
rm -rf "$root"
if [[ "$rc" -ne 0 ]]; then
  pass "fails fast (rc=$rc) instead of blocking on read without a TTY"
else
  fail "reported success despite multiple candidates and no way to choose"
fi

# 4. Empty device list entirely (flutter devices returned nothing at all).
root=$(mktemp -d -t omi_ios_dev_empty_XXXXXX)
stub_devices "$root" '[]'
out=$(run_selection "$root" 2>&1); rc=$?
rm -rf "$root"
if [[ "$rc" -ne 0 ]] && [[ "$out" == *"No iOS device or simulator found"* ]]; then
  pass "fails with a named error when no devices are connected at all"
else
  fail "expected a named no-iOS-device failure, got (rc=$rc): $out"
fi

echo "_ios_device_is_physical:"

run_physical_check() {
  local root="$1" device_id="$2"
  PATH="$root/bin" bash -c "source '$PHYSICAL_DEVICE_HARNESS'; _ios_device_is_physical '$device_id'"
}

# 5. A physical device's id reports true (regression: setup.sh ios silently
#    defaulted the dev backend host to 127.0.0.1 on physical devices, which is
#    the device's own loopback, not the Mac's — see issue #11534).
root=$(mktemp -d -t omi_ios_dev_physical_XXXXXX)
stub_devices "$root" '[
  {"name":"Revtim'"'"'s iPhone","id":"PHYS-1","isSupported":true,"targetPlatform":"ios","emulator":false},
  {"name":"iPhone 17 Pro","id":"SIM-2","isSupported":true,"targetPlatform":"ios","emulator":true}
]'
if run_physical_check "$root" "PHYS-1"; then
  pass "reports true for a physical device id"
else
  fail "expected true for physical device id PHYS-1"
fi

# 6. A simulator's id reports false.
if run_physical_check "$root" "SIM-2"; then
  fail "expected false for simulator id SIM-2"
else
  pass "reports false for a simulator id"
fi
rm -rf "$root"

echo
if [[ "$failures" -gt 0 ]]; then
  echo "$failures shell test(s) failed" >&2
  exit 1
fi
echo "all iOS device selection shell tests passed"
