#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESET="$ROOT/scripts/omi-local-profile-keychain-reset.sh"
RUN="$ROOT/run.sh"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/omi-local-profile-keychain-reset.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

BUNDLE_ID="com.omi.omi-keychain-reset-test"
APP="$TMP/omi-keychain-reset-test.app"
mkdir -p "$APP/Contents" "$TMP/bin"
plutil -create xml1 "$APP/Contents/Info.plist"
plutil -insert CFBundleIdentifier -string "$BUNDLE_ID" "$APP/Contents/Info.plist"

cat >"$TMP/bin/codesign" <<'SH'
#!/usr/bin/env bash
echo 'Executable=/tmp/omi-keychain-reset-test.app' >&2
echo 'TeamIdentifier=TESTTEAM123' >&2
SH
cat >"$TMP/bin/security" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$SECURITY_LOG"
exit "${SECURITY_EXIT_STATUS:-0}"
SH
chmod +x "$TMP/bin/codesign" "$TMP/bin/security"

export SECURITY_LOG="$TMP/security.log"
PATH="$TMP/bin:$PATH" "$RESET" "$BUNDLE_ID" "$APP" >/dev/null

EXPECTED="$TMP/expected.log"
cat >"$EXPECTED" <<EOF
delete-generic-password -s com.omi.desktop.firebase-rest-session.v2.team.TESTTEAM123.bundle.$BUNDLE_ID -a firebase-rest-tokens
delete-generic-password -s com.omi.desktop.local-agent-api.v2.team.TESTTEAM123.bundle.$BUNDLE_ID -a local-agent-api-token
delete-generic-password -s com.omi.client-device-id.v2.team.TESTTEAM123.bundle.$BUNDLE_ID -a install-uuid
EOF
diff -u "$EXPECTED" "$SECURITY_LOG"

: >"$SECURITY_LOG"
SECURITY_EXIT_STATUS=44 PATH="$TMP/bin:$PATH" "$RESET" "$BUNDLE_ID" "$APP" >/dev/null
test "$(wc -l <"$SECURITY_LOG" | tr -d ' ')" = "3"

if PATH="$TMP/bin:$PATH" "$RESET" com.omi.computer-macos "$APP" >/dev/null 2>&1; then
  echo "reset helper must reject the production bundle" >&2
  exit 1
fi

RUN_SRC="$(cat "$RUN")"
RESET_CALL='./scripts/omi-local-profile-keychain-reset.sh "$BUNDLE_ID" "$APP_PATH"'
if ! grep -Fq -- 'if [ "${OMI_DESKTOP_LOCAL_PROFILE:-0}" = "1" ]; then' <<<"$RUN_SRC"; then
  echo "run.sh must scope the reset to local-profile launches" >&2
  exit 1
fi
if ! grep -Fq -- "$RESET_CALL" <<<"$RUN_SRC"; then
  echo "run.sh must reset the installed local-profile bundle before launch" >&2
  exit 1
fi

python3 - "$RUN" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
reset = source.index('./scripts/omi-local-profile-keychain-reset.sh "$BUNDLE_ID" "$APP_PATH"')
launch = source.index('step "Starting app..."')
if reset >= launch:
    raise SystemExit("local-profile Keychain reset must run before app launch")
PY

echo "test-local-profile-keychain-reset.sh: OK"
