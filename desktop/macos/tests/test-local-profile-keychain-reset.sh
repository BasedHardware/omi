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
RESET_HELPER='reset_local_profile_keychain_state()'
if ! grep -Fq -- "$RESET_HELPER" <<<"$RUN_SRC"; then
  echo "run.sh must define the local-profile reset helper" >&2
  exit 1
fi
RESET_HELPER_BODY="$(sed -n "/$RESET_HELPER/,/^}/p" "$RUN")"
if ! grep -Fq -- 'if [ "$LOCAL_PROFILE" = true ]; then' <<<"$RESET_HELPER_BODY"; then
  echo "run.sh must scope the reset helper to local-profile launches" >&2
  exit 1
fi
if ! grep -Fq -- "$RESET_CALL" <<<"$RESET_HELPER_BODY"; then
  echo "run.sh must reset the installed local-profile bundle through the helper" >&2
  exit 1
fi

python3 - "$RUN" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
helper = "reset_local_profile_keychain_state"
if source.count(helper) != 3:
    raise SystemExit("local-profile reset helper must be called by both fast and full bundle paths")
fast = source.index('if [ "$FAST_BUNDLE" = "1" ]; then')
full = source.index('else\nstep "Preparing agent runtime..."', fast)
fast_call = source.index(helper, fast + len(helper))
full_call = source.index(helper, full + len(helper))
launch = source.index('step "Starting app..."')
if not fast < fast_call < full:
    raise SystemExit("fast bundle path must reset local-profile Keychain state")
if not full < full_call < launch:
    raise SystemExit("full bundle path must reset local-profile Keychain state before launch")
if fast_call >= launch or full_call >= launch:
    raise SystemExit("local-profile Keychain reset must run before app launch")
PY

echo "test-local-profile-keychain-reset.sh: OK"
