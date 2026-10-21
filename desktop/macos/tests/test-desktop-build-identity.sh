#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/desktop-build-identity.sh
source "$MACOS_DIR/scripts/desktop-build-identity.sh"

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-desktop-build-identity.XXXXXX")"
cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

REPOSITORY="$TMP_ROOT/repository"
PLIST="$TMP_ROOT/Info.plist"
mkdir -p "$REPOSITORY"
git -C "$REPOSITORY" init -q
git -C "$REPOSITORY" -c user.name='Omi Test' -c user.email='omi-test@example.invalid' \
  commit --allow-empty -qm 'seed'

python3 - "$PLIST" <<'PY'
import plistlib
import sys

with open(sys.argv[1], "wb") as destination:
    plistlib.dump({"CFBundleIdentifier": "com.omi.test"}, destination)
PY

REVISION="$(git -C "$REPOSITORY" rev-parse HEAD)"
omi_stamp_desktop_build_identity "$REPOSITORY" "$PLIST"
python3 - "$PLIST" "$REVISION" clean <<'PY'
import plistlib
import sys

with open(sys.argv[1], "rb") as source:
    metadata = plistlib.load(source)
assert metadata["OMIBuildIdentitySchemaVersion"] == 1
assert metadata["OMISourceRevision"] == sys.argv[2]
assert metadata["OMISourceWorkingTreeState"] == sys.argv[3]
assert metadata["CFBundleIdentifier"] == "com.omi.test"
PY

printf 'dirty\n' >"$REPOSITORY/uncommitted.txt"
omi_stamp_desktop_build_identity "$REPOSITORY" "$PLIST"
python3 - "$PLIST" "$REVISION" dirty <<'PY'
import plistlib
import sys

with open(sys.argv[1], "rb") as source:
    metadata = plistlib.load(source)
assert metadata["OMISourceRevision"] == sys.argv[2]
assert metadata["OMISourceWorkingTreeState"] == sys.argv[3]
PY

NON_REPOSITORY="$TMP_ROOT/not-a-repository"
mkdir -p "$NON_REPOSITORY"
omi_stamp_desktop_build_identity "$NON_REPOSITORY" "$PLIST"
python3 - "$PLIST" <<'PY'
import plistlib
import sys

with open(sys.argv[1], "rb") as source:
    metadata = plistlib.load(source)
assert metadata["OMISourceRevision"] == "unknown"
assert metadata["OMISourceWorkingTreeState"] == "unknown"
PY

EXPECTED_IDENTITY="$(omi_desktop_build_identity "$REPOSITORY")"
HEALTH="$(python3 - "$EXPECTED_IDENTITY" <<'PY'
import json
import sys

print(json.dumps({
    "ok": True,
    "bundleIdentifier": "com.omi.omi-identity-test",
    "sourceIdentity": json.loads(sys.argv[1]),
    "agentRuntimeRunning": True,
    "agentRuntimeExpectedProtocolVersion": 3,
    "agentRuntimeProtocolVersion": 3,
    "agentRuntimeVersion": "test",
}, separators=(",", ":")))
PY
)"
python3 "$MACOS_DIR/scripts/desktop-health-check.py" \
  --expected-bundle com.omi.omi-identity-test \
  --health-json "$HEALTH" \
  --expected-source-identity "$EXPECTED_IDENTITY" \
  --require-protocol >/dev/null

STALE_IDENTITY='{"revision":"ffffffffffffffffffffffffffffffffffffffff","schemaVersion":1,"workingTreeState":"dirty"}'
if python3 "$MACOS_DIR/scripts/desktop-health-check.py" \
  --expected-bundle com.omi.omi-identity-test \
  --health-json "$HEALTH" \
  --expected-source-identity "$STALE_IDENTITY" \
  --require-protocol >/dev/null 2>&1; then
  echo "health check accepted a bundle built from a different source identity" >&2
  exit 1
fi

UNKNOWN_IDENTITY='{"revision":"unknown","schemaVersion":1,"workingTreeState":"unknown"}'
if python3 "$MACOS_DIR/scripts/desktop-health-check.py" \
  --expected-bundle com.omi.omi-identity-test \
  --health-json "$HEALTH" \
  --expected-source-identity "$UNKNOWN_IDENTITY" \
  --require-protocol >/dev/null 2>&1; then
  echo "health check accepted unknown as revision-specific evidence" >&2
  exit 1
fi

echo "desktop build identity tests passed"
