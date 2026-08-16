#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT="$MACOS_DIR/scripts/desktop-doctor-preflight.py"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

mkdir -p "$TMPDIR/bin" "$TMPDIR/desktop/macos/pi-mono-extension" "$TMPDIR/desktop/macos/tmp"
touch "$TMPDIR/desktop/macos/pi-mono-extension/package.json"

cat >"$TMPDIR/bin/xcrun" <<'SH'
#!/usr/bin/env bash
echo "swift-driver version test"
SH
cat >"$TMPDIR/bin/cargo" <<'SH'
#!/usr/bin/env bash
echo "cargo 1.0.0"
SH
cat >"$TMPDIR/bin/node" <<'SH'
#!/usr/bin/env bash
echo "v20.0.0"
SH
cat >"$TMPDIR/bin/npm" <<'SH'
#!/usr/bin/env bash
echo "10.0.0"
SH
cat >"$TMPDIR/bin/agent-swift" <<'SH'
#!/usr/bin/env bash
echo "agent-swift test"
SH
chmod +x "$TMPDIR/bin/"*

cat >"$TMPDIR/desktop/macos/tmp/desktop-auth.json" <<'JSON'
{
  "auth_isSignedIn": {"value": true},
  "auth_idToken": {"value": "token"},
  "auth_userEmail": {"value": "dev@example.com"}
}
JSON

PATH="$TMPDIR/bin:$PATH" "$SCRIPT" --root "$TMPDIR" --require-auth-seed >"$TMPDIR/pass.out" 2>"$TMPDIR/pass.err" || \
  fail "doctor preflight unexpectedly failed with fake prerequisites"
grep -q "PASS xcrun SwiftPM" "$TMPDIR/pass.out" || fail "xcrun check missing"
grep -q "PASS auth seed" "$TMPDIR/pass.out" || fail "auth seed check missing"
grep -q "SKIP automation bridge" "$TMPDIR/pass.out" || fail "bridge skip missing"

rm "$TMPDIR/desktop/macos/tmp/desktop-auth.json"
if PATH="$TMPDIR/bin:$PATH" "$SCRIPT" --root "$TMPDIR" --require-auth-seed >"$TMPDIR/fail.out" 2>"$TMPDIR/fail.err"; then
  fail "doctor preflight unexpectedly passed without required auth seed"
fi
grep -q "FAIL auth seed" "$TMPDIR/fail.out" || fail "missing auth seed was not reported"
grep -q "required desktop verification prerequisite" "$TMPDIR/fail.err" || fail "failure summary missing"

if OMI_AUTOMATION_PORT=not-a-port PATH="$TMPDIR/bin:$PATH" "$SCRIPT" --root "$TMPDIR" --require-bridge \
    >"$TMPDIR/bad-port.out" 2>"$TMPDIR/bad-port.err"; then
  fail "doctor preflight unexpectedly passed with an invalid automation port"
fi
grep -q "FAIL automation bridge: invalid automation port: 'not-a-port'" "$TMPDIR/bad-port.out" || \
  fail "invalid automation port was not reported as a normal check failure"

python3 - "$SCRIPT" <<'PY'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("doctor", sys.argv[1])
doctor = importlib.util.module_from_spec(spec)
sys.modules["doctor"] = doctor
spec.loader.exec_module(doctor)

failure = doctor.bridge_payload_result('{"state":"not an automation response"}', 47777)
assert failure is not None
assert failure.status == "FAIL"
assert "ok=true" in failure.detail

success = doctor.bridge_payload_result('{"ok": true, "result": {}}', 47777)
assert success is None
PY

echo "desktop doctor preflight tests passed"
