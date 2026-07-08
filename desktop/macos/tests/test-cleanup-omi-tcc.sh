#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT="$MACOS_DIR/scripts/cleanup-omi-tcc.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

home="$TMPDIR/home"
apps="$TMPDIR/apps"
prefs="$home/Library/Preferences"
tcc_dir="$home/Library/Application Support/com.apple.TCC"
bin="$TMPDIR/bin"
mkdir -p "$apps" "$prefs" "$tcc_dir" "$bin"

make_app() {
  local app_name="$1" bundle_id="$2" display_name="$3"
  local contents="$apps/$app_name.app/Contents"
  mkdir -p "$contents"
  python3 - "$contents/Info.plist" "$bundle_id" "$display_name" <<'PY'
import plistlib
import sys

path, bundle_id, display_name = sys.argv[1:]
with open(path, "wb") as handle:
    plistlib.dump(
        {
            "CFBundleIdentifier": bundle_id,
            "CFBundleDisplayName": display_name,
            "CFBundleName": display_name,
        },
        handle,
    )
PY
}

make_pref() {
  local domain="$1"
  python3 - "$prefs/$domain.plist" <<'PY'
import plistlib
import sys

with open(sys.argv[1], "wb") as handle:
    plistlib.dump({"fixture": True}, handle)
PY
}

make_app "Omi" "com.omi.computer-macos" "Omi"
make_app "Omi Dev" "com.omi.desktop-dev" "Omi Dev"
make_app "omi-test-one" "com.omi.omi-test-one" "omi-test-one"
make_app "omi-review" "com.omi.review-build" "omi-review"
make_app "Other" "com.example.other" "Other"
make_pref "com.omi.omi-pref-only"
make_pref "com.omi.review-pref"

python3 - "$tcc_dir/TCC.db" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.execute(
    "CREATE TABLE access (service TEXT, client TEXT, client_type INTEGER, auth_value INTEGER, last_modified INTEGER)"
)
conn.executemany(
    "INSERT INTO access VALUES (?, ?, ?, ?, ?)",
    [
        ("kTCCServiceMicrophone", "com.omi.omi-test-one", 0, 2, 1),
        ("kTCCServiceScreenCapture", "com.omi.omi-pref-only", 0, 2, 1),
        ("kTCCServiceMicrophone", "com.omi.desktop-dev", 0, 2, 1),
        ("kTCCServiceMicrophone", "com.omi.review-build", 0, 2, 1),
        ("kTCCServiceMicrophone", "/Applications/Omi.app/Contents/MacOS/Omi", 1, 2, 1),
        ("kTCCServiceMicrophone", "/Applications/Omi Dev.app/Contents/MacOS/Omi", 1, 2, 1),
        ("kTCCServiceMicrophone", "/Applications/omi-path-only.app/Contents/MacOS/Omi", 1, 2, 1),
    ],
)
conn.commit()
conn.close()
PY

json_out="$TMPDIR/inventory.json"
OMI_TCC_HOME="$home" OMI_TCC_APP_ROOTS="$apps" "$SCRIPT" --json >"$json_out"

python3 - "$json_out" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1]))
assert data["tcc"]["readable"] is True
assert data["candidate_prefixes"] == ["com.omi.omi-"]
assert data["tccutil_bundle_ids"] == ["com.omi.omi-test-one"], data["tccutil_bundle_ids"]
assert set(data["candidate_bundle_ids"]) == {"com.omi.omi-test-one", "com.omi.omi-pref-only"}
assert "com.omi.computer-macos" in data["keep_bundle_ids"]
assert "com.omi.desktop-dev" in data["keep_bundle_ids"]
assert data["summary"]["apps"].get("keep") == 2, data["summary"]
assert data["summary"]["apps"].get("candidate") == 1, data["summary"]
assert data["summary"]["apps"].get("review") == 1, data["summary"]
tcc_classes = {row["client"]: row["classification"] for row in data["tcc"]["rows"]}
assert tcc_classes["/Applications/Omi.app/Contents/MacOS/Omi"] == "keep", tcc_classes
assert tcc_classes["/Applications/Omi Dev.app/Contents/MacOS/Omi"] == "keep", tcc_classes
assert tcc_classes["/Applications/omi-path-only.app/Contents/MacOS/Omi"] == "candidate", tcc_classes
PY

cat >"$bin/tccutil" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$TCCUTIL_LOG"
exit 0
SH
chmod +x "$bin/tccutil"
apply_json="$TMPDIR/apply.json"
TCCUTIL_LOG="$TMPDIR/tccutil.log" \
PATH="$bin:$PATH" \
OMI_TCC_HOME="$home" \
OMI_TCC_APP_ROOTS="$apps" \
  "$SCRIPT" --apply-tccutil --json >"$apply_json"

python3 - "$apply_json" "$TMPDIR/tccutil.log" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1]))
log = open(sys.argv[2]).read().splitlines()
assert log == ["reset All com.omi.omi-test-one"], log
assert data["apply"]["summary"] == {"ok": 1}, data["apply"]
PY

custom_json="$TMPDIR/custom.json"
OMI_TCC_HOME="$home" OMI_TCC_APP_ROOTS="$apps" \
  "$SCRIPT" --json --candidate-prefix com.omi.review- --keep-bundle-id com.omi.review-build >"$custom_json"
python3 - "$custom_json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1]))
# Explicit keep wins over a broader candidate prefix.
assert "com.omi.review-build" in data["keep_bundle_ids"]
assert data["tccutil_bundle_ids"] == ["com.omi.omi-test-one"], data["tccutil_bundle_ids"]
PY

if "$SCRIPT" --candidate-prefix org.example. >/tmp/cleanup-omi-tcc-invalid.out 2>/tmp/cleanup-omi-tcc-invalid.err; then
  fail "invalid non-Omi candidate prefix unexpectedly succeeded"
fi
if ! grep -q "expected an Omi bundle ID" /tmp/cleanup-omi-tcc-invalid.err; then
  fail "invalid candidate prefix did not explain Omi bundle ID requirement"
fi

echo "cleanup-omi-tcc tests passed"
