#!/usr/bin/env bash
# Hermetic checks: named-bundle auth seed must not CLI-write Keychain tokens
# (apple-tool: partition → login-keychain password sheet on app read), and a
# developer target must get its tokens in the developer-secrets file only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED="$ROOT/scripts/omi-auth-seed.sh"
RUN="$ROOT/run.sh"
FAIL=0

assert_contains() {
  local haystack="$1" needle="$2" msg="$3"
  if ! grep -Fq -- "$needle" <<<"$haystack"; then
    echo "FAIL: $msg" >&2
    echo "  missing: $needle" >&2
    FAIL=1
  fi
}

assert_not_contains() {
  local haystack="$1" needle="$2" msg="$3"
  if grep -Fq -- "$needle" <<<"$haystack"; then
    echo "FAIL: $msg" >&2
    echo "  unexpected: $needle" >&2
    FAIL=1
  fi
}

SEED_SRC="$(cat "$SEED")"
RUN_SRC="$(cat "$RUN")"

assert_contains "$SEED_SRC" 'delete-generic-password' \
  "omi-auth-seed.sh must clear any prior CLI-written Keychain item before launch"
assert_contains "$SEED_SRC" 'auth_idToken' \
  "omi-auth-seed.sh must seed auth_idToken (UserDefaults for shipped targets, secrets file otherwise)"
assert_contains "$SEED_SRC" 'UserDefaults' \
  "omi-auth-seed.sh must document/use the UserDefaults → Keychain migrate path"
# Match a real security invocation, not explanatory comments that name the flag.
assert_not_contains "$SEED_SRC" 'security", "add-generic-password' \
  "omi-auth-seed.sh must not invoke security add-generic-password (apple-tool: partition prompts)"
assert_not_contains "$SEED_SRC" 'security add-generic-password' \
  "omi-auth-seed.sh must not invoke security add-generic-password (apple-tool: partition prompts)"
assert_contains "$RUN_SRC" 'omi-auth-seed.sh "$BUNDLE_ID" "$AUTH_CACHE" "$APP_PATH"' \
  "run.sh must pass the just-installed APP_PATH into omi-auth-seed.sh"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/omi-auth-seed-acl.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
cat >"$TMP/auth.json" <<'JSON'
{
  "auth_idToken": {"type": "string", "value": "id-token-seed"},
  "auth_refreshToken": {"type": "string", "value": "refresh-token-seed"},
  "auth_tokenExpiry": {"type": "string", "value": "9999999999"},
  "auth_tokenUserId": {"type": "string", "value": "uid-seed"},
  "auth_isSignedIn": {"type": "boolean", "value": "1"},
  "auth_userEmail": {"type": "string", "value": "seed@example.com"}
}
JSON

# Use a throwaway defaults domain + fake team via missing app (adhoc.<bundle>).
# A developer target persists tokens in its developer-secrets file (never the
# keychain, never UserDefaults); HOME is redirected so the file lands in $TMP.
BID="com.omi.omi-acl-seed-ud-$$"
defaults delete "$BID" >/dev/null 2>&1 || true
mkdir -p "$TMP/home"
HOME="$TMP/home" "$SEED" "$BID" "$TMP/auth.json" >/dev/null
ID="$(defaults read "$BID" auth_idToken 2>/dev/null || true)"
REFRESH="$(defaults read "$BID" auth_refreshToken 2>/dev/null || true)"
SIGNED="$(defaults read "$BID" auth_isSignedIn 2>/dev/null || true)"
defaults delete "$BID" >/dev/null 2>&1 || true
SECRETS="$TMP/home/Library/Application Support/Omi Dev Bundles/$BID/developer-secrets/$BID.json"

if [ -n "$ID" ] || [ -n "$REFRESH" ]; then
  echo "FAIL: developer seed must not leave token keys in UserDefaults (id='$ID' refresh='$REFRESH')" >&2
  FAIL=1
fi
if [ ! -f "$SECRETS" ]; then
  echo "FAIL: expected developer secrets file at $SECRETS" >&2
  FAIL=1
else
  MODE="$(stat -f '%Lp' "$SECRETS")"
  if [ "$MODE" != "600" ]; then
    echo "FAIL: developer secrets file must be mode 600 (got $MODE)" >&2
    FAIL=1
  fi
  if ! grep -Fq 'id-token-seed' "$SECRETS" || ! grep -Fq 'firebase-rest-tokens' "$SECRETS"; then
    echo "FAIL: developer secrets file must carry the seeded tokens under the firebase-rest-tokens account" >&2
    FAIL=1
  fi
fi
if [ "$SIGNED" != "1" ] && [ "$SIGNED" != "true" ]; then
  echo "FAIL: expected auth_isSignedIn after seed (got '$SIGNED')" >&2
  FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
  echo "test-omi-auth-seed-acl.sh: FAILED" >&2
  exit 1
fi
echo "test-omi-auth-seed-acl.sh: OK"
