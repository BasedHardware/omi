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

# ── E2E pool slots are not local-emulator profiles: refuse, any slot id ────
# A pool slot's keychain item holds the session a human signed in once and
# must survive every rebuild; the reset helper must refuse it outright, for
# any pool size (slot 7 exists the moment the pool is grown), before it even
# looks at the app.
for pool_id in com.omi.omi-e2e-1 com.omi.omi-e2e-2 com.omi.omi-e2e-7; do
  if PATH="$TMP/bin:$PATH" "$RESET" "$pool_id" "$APP" >/dev/null 2>&1; then
    echo "reset helper must refuse E2E pool slot $pool_id" >&2
    exit 1
  fi
done
if out="$(PATH="$TMP/bin:$PATH" "$RESET" com.omi.omi-e2e-3 "$TMP/missing.app" 2>&1)"; then
  echo "reset helper must refuse a pool slot before touching the app" >&2
  exit 1
fi
case "$out" in
  *"pool slot"*) ;;
  *) echo "pool refusal must say it refused a pool slot: $out" >&2; exit 1 ;;
esac
if OMI_E2E_POOL_PREFIX=omi-lab PATH="$TMP/bin:$PATH" "$RESET" com.omi.omi-lab-12 "$APP" >/dev/null 2>&1; then
  echo "reset helper must refuse a configured-prefix pool slot" >&2
  exit 1
fi

echo "test-local-profile-keychain-reset.sh: OK"
