#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLI="$MACOS_DIR/scripts/omi-macos-dev"

TMPDIR="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

home="$TMPDIR/home"
apps="$TMPDIR/apps"
logs="$TMPDIR/logs"
bin="$TMPDIR/bin"
mkdir -p "$home" "$apps" "$logs" "$bin"

make_app() {
  local name="$1" bundle_id="$2"
  mkdir -p "$apps/$name.app/Contents"
  python3 - "$apps/$name.app/Contents/Info.plist" "$bundle_id" "$name" <<'PY'
import plistlib
import sys
with open(sys.argv[1], "wb") as handle:
    plistlib.dump({"CFBundleIdentifier": sys.argv[2], "CFBundleDisplayName": sys.argv[3]}, handle)
PY
}

make_manifest() {
  local bundle_id="$1" profile="$2" profile_root="$3"
  mkdir -p "$profile/users/test-user"
  printf 'sqlite-fixture' >"$profile/users/test-user/omi.db"
  python3 - "$profile/.omi-dev-runtime.json" "$bundle_id" "$profile_root" <<'PY'
import json
import sys
payload = {
    "schemaVersion": 1,
    "bundleIdentifier": sys.argv[2],
    "processID": 999999,
    "startedAt": "2026-01-01T00:00:00Z",
    "appPath": "/Applications/fixture.app",
    "profileRoot": sys.argv[3],
    "logPath": "/private/tmp/fixture.log",
    "automationPort": 47777,
}
json.dump(payload, open(sys.argv[1], "w"), sort_keys=True)
PY
}

cat >"$bin/lsof" <<'SH'
#!/usr/bin/env bash
exit 1
SH
chmod +x "$bin/lsof"

good_id="com.omi.omi-good"
old_id="com.omi.omi-old"
shared_id="com.omi.omi-shared"
support="$home/Library/Application Support/Omi Dev Bundles"
legacy="$home/Library/Application Support/Omi"

make_app "omi-good" "$good_id"
make_app "omi-old" "$old_id"
make_app "Omi Dev" "com.omi.desktop-dev"
make_app "invalid-named" "com.omi.omi-../escape"
make_manifest "$good_id" "$support/$good_id" "$support/$good_id"
make_manifest "$old_id" "$support/$old_id" "$support/$old_id"
make_manifest "$shared_id" "$support/$shared_id" "$legacy"
mkdir -p "$legacy"
printf 'protected shared data' >"$legacy/omi.db"
printf 'old log' >"$logs/omi-dev-$old_id-321.log"
printf 'protected dev log' >"$logs/omi-dev-com.omi.desktop-dev-777.log"

python3 - "$apps/omi-old.app" "$support/$old_id" "$logs/omi-dev-$old_id-321.log" "$logs/omi-dev-com.omi.desktop-dev-777.log" <<'PY'
import os
import sys
import time
then = time.time() - 40 * 86400
for path in sys.argv[1:]:
    os.utime(path, (then, then))
PY

env=(
  OMI_MACOS_DEV_HOME="$home"
  OMI_MACOS_DEV_APP_ROOTS="$apps"
  OMI_MACOS_DEV_LOG_ROOTS="$logs"
  OMI_MACOS_DEV_LSOF="$bin/lsof"
)

doctor="$TMPDIR/doctor.json"
env "${env[@]}" "$CLI" doctor --bundle "$good_id" >"$doctor"
python3 - "$doctor" "$good_id" "$support" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["diagnostic"] is None, payload
record = payload["bundles"][0]
assert record["bundle_id"] == sys.argv[2]
assert record["isolation"] == "isolated", record
assert record["profile_root"] == f"{sys.argv[3]}/{sys.argv[2]}"
assert record["databases"][0]["holders"] == []
assert record["backend"]["status"] == "unavailable"
PY

if env "${env[@]}" "$CLI" doctor --bundle "$shared_id" >"$TMPDIR/shared.json"; then
  echo "FAIL: shared legacy profile unexpectedly passed doctor" >&2
  exit 1
fi
python3 - "$TMPDIR/shared.json" "$shared_id" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["diagnostic"] == "shared_named_bundle_storage", payload
assert payload["shared_storage_bundle_ids"] == [sys.argv[2]], payload
PY

env "${env[@]}" "$CLI" logs list >"$TMPDIR/logs.json"
python3 - "$TMPDIR/logs.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert len(payload["logs"]) == 1, payload
PY

env "${env[@]}" "$CLI" clean plan --older-than 14 >"$TMPDIR/plan.json"
plan="$(python3 - "$TMPDIR/plan.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
kinds = {item["kind"] for item in payload["actions"]}
assert {"delete_bundle", "delete_profile", "delete_log"}.issubset(kinds), payload
assert payload["legacy_shared_root_touched"] is False
print(payload["plan"])
PY
)"

if env "${env[@]}" "$CLI" clean apply --older-than 14 --plan not-the-plan --yes >/dev/null; then
  echo "FAIL: mismatched cleanup plan unexpectedly applied" >&2
  exit 1
fi

env "${env[@]}" "$CLI" clean apply --older-than 14 --plan "$plan" --yes >"$TMPDIR/applied.json"
test ! -e "$apps/omi-old.app"
test ! -e "$support/$old_id"
test ! -e "$logs/omi-dev-$old_id-321.log"
test -f "$legacy/omi.db"
test -d "$apps/Omi Dev.app"
test -d "$apps/invalid-named.app"
test -f "$logs/omi-dev-com.omi.desktop-dev-777.log"

echo "omi-macos-dev tests passed"
