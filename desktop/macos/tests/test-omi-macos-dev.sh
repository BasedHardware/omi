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
prefs="$home/Library/Preferences"
tcc_dir="$home/Library/Application Support/com.apple.TCC"
mkdir -p "$home" "$apps" "$logs" "$bin" "$prefs" "$tcc_dir"

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
for ((index = 1; index <= 24; index++)); do
  mkdir -p "$legacy/users/test-$index"
  printf 'legacy test data' >"$legacy/users/test-$index/omi.db"
  printf 'preference fixture' >"$prefs/com.omi.omi-preference-$index.plist"
  printf 'recent log' >"$logs/omi-dev-com.omi.omi-extra-$index-321.log"
done
printf 'old log' >"$logs/omi-dev-$old_id-321.log"
printf 'protected dev log' >"$logs/omi-dev-com.omi.desktop-dev-777.log"

python3 - "$tcc_dir/TCC.db" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE access (service TEXT, client TEXT, auth_value INTEGER)")
conn.execute("INSERT INTO access VALUES (?, ?, ?)", ("kTCCServiceMicrophone", "com.omi.omi-good", 2))
conn.commit()
conn.close()
PY

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
assert payload["detail_mode"] == "summary", payload
assert payload["details_available"] is True, payload
assert payload["legacy_database_summary"]["count"] == 25, payload
record = payload["bundles"][0]
assert record["bundle_id"] == sys.argv[2]
assert record["isolation"] == "isolated", record
assert record["profile_root"] == f"{sys.argv[3]}/{sys.argv[2]}"
assert record["database_summary"]["holder_pids"] == []
assert record["backend"]["status"] == "unavailable"
assert "databases" not in record, record
assert "legacy_databases" not in payload, payload
PY

env "${env[@]}" "$CLI" doctor --bundle "$good_id" --verbose >"$TMPDIR/doctor-verbose.json"
python3 - "$TMPDIR/doctor-verbose.json" "$good_id" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "full", payload
assert len(payload["legacy_databases"]) == 25, payload
record = payload["bundles"][0]
assert record["bundle_id"] == sys.argv[2]
assert record["databases"][0]["holders"] == []
PY

env "${env[@]}" "$CLI" bundle list >"$TMPDIR/bundles.json"
python3 - "$TMPDIR/bundles.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "summary", payload
assert payload["bundle_summary"]["count"] >= 3, payload
assert "legacy_databases" not in payload, payload
PY

env "${env[@]}" "$CLI" bundle list --verbose >"$TMPDIR/bundles-verbose.json"
python3 - "$TMPDIR/bundles-verbose.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "full", payload
assert len(payload["legacy_databases"]) == 25, payload
assert len(payload["bundles"]) >= 3, payload
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
assert payload["detail_mode"] == "summary", payload
assert payload["log_summary"]["count"] == 25, payload
assert "logs" not in payload, payload
PY

env "${env[@]}" "$CLI" logs list --verbose >"$TMPDIR/logs-verbose.json"
python3 - "$TMPDIR/logs-verbose.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "full", payload
assert len(payload["logs"]) == 25, payload
PY

env "${env[@]}" "$CLI" logs prune --older-than 14 >"$TMPDIR/log-prune.json"
python3 - "$TMPDIR/log-prune.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "summary", payload
assert payload["action_summary"]["count"] == 1, payload
assert "actions" not in payload, payload
PY

env "${env[@]}" "$CLI" logs prune --older-than 14 --verbose >"$TMPDIR/log-prune-verbose.json"
python3 - "$TMPDIR/log-prune-verbose.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "full", payload
assert len(payload["actions"]) == 1, payload
assert payload["retained"] == [], payload
PY

env "${env[@]}" "$CLI" permissions list >"$TMPDIR/permissions.json"
python3 - "$TMPDIR/permissions.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "summary", payload
assert payload["summary"]["preferences"]["candidate"] == 24, payload
assert payload["tcc"]["row_count"] == 1, payload
assert "preferences" not in payload, payload
PY

env "${env[@]}" "$CLI" permissions list --verbose >"$TMPDIR/permissions-verbose.json"
python3 - "$TMPDIR/permissions-verbose.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "full", payload
assert len(payload["preferences"]) == 24, payload
assert len(payload["tcc"]["rows"]) == 1, payload
PY

env "${env[@]}" "$CLI" clean plan --older-than 14 >"$TMPDIR/plan.json"
plan="$(python3 - "$TMPDIR/plan.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "summary", payload
assert payload["action_summary"]["kind_counts"] == {"delete_bundle": 1, "delete_log": 1, "delete_profile": 1}, payload
assert payload["legacy_shared_root_touched"] is False
print(payload["plan"])
PY
)"

env "${env[@]}" "$CLI" clean plan --older-than 14 --verbose >"$TMPDIR/plan-verbose.json"
python3 - "$TMPDIR/plan-verbose.json" "$plan" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
kinds = {item["kind"] for item in payload["actions"]}
assert payload["detail_mode"] == "full", payload
assert payload["plan"] == sys.argv[2], payload
assert {"delete_bundle", "delete_profile", "delete_log"}.issubset(kinds), payload
PY

if env "${env[@]}" "$CLI" clean apply --older-than 14 --plan not-the-plan --yes >/dev/null; then
  echo "FAIL: mismatched cleanup plan unexpectedly applied" >&2
  exit 1
fi

env "${env[@]}" "$CLI" clean apply --older-than 14 --plan "$plan" --yes >"$TMPDIR/applied.json"
python3 - "$TMPDIR/applied.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["detail_mode"] == "summary", payload
assert payload["completed_summary"]["count"] == 3, payload
assert "completed" not in payload, payload
PY
test ! -e "$apps/omi-old.app"
test ! -e "$support/$old_id"
test ! -e "$logs/omi-dev-$old_id-321.log"
test -f "$legacy/omi.db"
test -d "$apps/Omi Dev.app"
test -d "$apps/invalid-named.app"
test -f "$logs/omi-dev-com.omi.desktop-dev-777.log"

if env "${env[@]}" "$CLI" clean plan --older-than -1 >/dev/null; then
  echo "FAIL: negative cleanup age unexpectedly succeeded" >&2
  exit 1
fi
recent_id="com.omi.omi-immediate"
make_app "omi-immediate" "$recent_id"
make_manifest "$recent_id" "$support/$recent_id" "$support/$recent_id"
printf 'immediate cleanup log' >"$logs/omi-dev-$recent_id-321.log"

env "${env[@]}" "$CLI" clean plan --older-than 0 >"$TMPDIR/immediate-plan.json"
immediate_plan="$(python3 - "$TMPDIR/immediate-plan.json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["older_than_days"] == 0, payload
assert payload["detail_mode"] == "summary", payload
assert payload["action_summary"]["kind_counts"]["delete_bundle"] >= 2, payload
assert payload["action_summary"]["kind_counts"]["delete_profile"] >= 2, payload
assert payload["action_summary"]["kind_counts"]["delete_log"] >= 1, payload
print(payload["plan"])
PY
)"

env "${env[@]}" "$CLI" clean plan --older-than 0 --verbose >"$TMPDIR/immediate-plan-verbose.json"
python3 - "$TMPDIR/immediate-plan-verbose.json" "$immediate_plan" "$apps/omi-immediate.app" "$support/$recent_id" "$logs/omi-dev-$recent_id-321.log" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
paths = {item["path"] for item in payload["actions"]}
assert payload["detail_mode"] == "full", payload
assert payload["plan"] == sys.argv[2], payload
assert set(sys.argv[3:]).issubset(paths), payload
PY

env "${env[@]}" "$CLI" clean apply --older-than 0 --plan "$immediate_plan" --yes --verbose >"$TMPDIR/immediate-applied.json"
python3 - "$TMPDIR/immediate-applied.json" "$apps/omi-immediate.app" "$support/$recent_id" "$logs/omi-dev-$recent_id-321.log" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
paths = {item["path"] for item in payload["completed"]}
assert payload["detail_mode"] == "full", payload
assert set(sys.argv[2:]).issubset(paths), payload
PY
test ! -e "$apps/omi-immediate.app"
test ! -e "$support/$recent_id"
test ! -e "$logs/omi-dev-$recent_id-321.log"
test -f "$legacy/omi.db"
test -d "$apps/Omi Dev.app"
test -f "$logs/omi-dev-com.omi.desktop-dev-777.log"

bash "$MACOS_DIR/tests/test-cleanup-omi-tcc.sh"

echo "omi-macos-dev tests passed"
