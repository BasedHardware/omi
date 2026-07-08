#!/bin/bash
# omi-auth-seed.sh — replay a captured auth session into a test bundle.
#
# Writes the auth-state UserDefaults keys (isSignedIn, userEmail, userId,
# names, onboarding) captured by omi-auth-dump.sh into the target bundle's
# domain. Auth tokens (idToken, refreshToken, expiry, tokenUserId) live in the
# login Keychain under a Team-ID-scoped service name (see
# DesktopKeychainStore.scopedService). Named test bundles signed with the same
# Apple Development team as Omi Dev share that scoped item — no per-bundle
# Keychain seed is needed when the dump came from the same team.
#
# If the dump captured tokens from UserDefaults (pre-migration source) or the
# target team differs, those token values are written into the target team's
# scoped Keychain item so the target bundle can read them on launch.
#
# Run this BEFORE launching the bundle (UserDefaults is read at startup).
#
# Usage: omi-auth-seed.sh <target-bundle-id> [in-file]
#   target-bundle-id  e.g. com.omi.omi-fix-rewind  (a named test bundle)
#   in-file           default: desktop/tmp/desktop-auth.json
set -euo pipefail

TARGET="${1:?usage: omi-auth-seed.sh <target-bundle-id> [in-file]}"
IN="${2:-$(cd "$(dirname "$0")/.." && pwd)/tmp/desktop-auth.json}"

[ "$TARGET" != "com.omi.computer-macos" ] || {
  echo "Refusing to seed production auth; shipped bundles store Firebase tokens in Keychain." >&2
  exit 1
}

[ -f "$IN" ] || { echo "No auth file at $IN — run omi-auth-dump.sh first." >&2; exit 1; }

KC_SERVICE_BASE="com.omi.desktop.firebase-rest-session"
KC_ACCOUNT="firebase-rest-tokens"

resolve_app_path() {
  local bid="$1"
  local path
  path="$(mdfind "kMDItemCFBundleIdentifier == '$bid'" 2>/dev/null | head -1 || true)"
  if [ -n "$path" ] && [ -d "$path" ]; then
    printf '%s\n' "$path"
    return 0
  fi
  for candidate in \
    "/Applications/Omi Dev.app" \
    "/Applications/${bid#com.omi.}.app" \
    "/Applications/omi.app"
  do
    if [ -d "$candidate" ]; then
      local found
      found="$(defaults read "$candidate/Contents/Info" CFBundleIdentifier 2>/dev/null || true)"
      if [ "$found" = "$bid" ]; then
        printf '%s\n' "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

APP_PATH="$(resolve_app_path "$TARGET" || true)"
TEAM_ID=""
if [ -n "$APP_PATH" ]; then
  TEAM_ID="$(codesign -dv --verbose=4 "$APP_PATH" 2>&1 | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
fi
if [ -z "$TEAM_ID" ] || [ "$TEAM_ID" = "not set" ]; then
  TEAM_ID="adhoc.${TARGET}"
fi
KC_SERVICE="${KC_SERVICE_BASE}.v2.team.${TEAM_ID}"

# Token secrets are never written to the target bundle's UserDefaults — that
# was the plaintext path this PR removed. If tokens are present in the dump,
# they are written to the team-scoped Keychain item.
SKIP_KEYS="auth_idToken auth_refreshToken auth_tokenExpiry auth_tokenUserId _keychainService"

python3 - "$TARGET" "$IN" "$SKIP_KEYS" "$KC_SERVICE" "$KC_ACCOUNT" <<'PY'
import json, subprocess, sys

target, inp = sys.argv[1], sys.argv[2]
skip = set(sys.argv[3].split())
kc_service, kc_account = sys.argv[4], sys.argv[5]
data = json.load(open(inp))

flag = {"boolean": "-bool", "string": "-string", "integer": "-int",
        "float": "-float", "date": "-date", "data": "-data"}

n = 0
for k, info in data.items():
    if k in skip:
        continue
    typ, val = info["type"], info["value"]
    # `defaults read` prints booleans as 1/0, but `defaults write -bool` only
    # accepts true/false/yes/no — convert so the write doesn't fail.
    if typ == "boolean":
        val = "true" if val.strip().lower() in ("1", "true", "yes") else "false"
    subprocess.run(["defaults", "write", target, k, flag.get(typ, "-string"), val], check=True)
    n += 1
print(f"Seeded {n} keys into {target}")

# Write token blob into the target team's scoped Keychain item. Same-team dumps
# already share the item; this still refreshes the blob when the dump carried
# explicit token values (pre-migration source or cross-team seed).
id_token = data.get("auth_idToken", {}).get("value", "")
refresh_token = data.get("auth_refreshToken", {}).get("value", "")
token_expiry = data.get("auth_tokenExpiry", {}).get("value", "0")
token_uid = data.get("auth_tokenUserId", {}).get("value", "")

if id_token and refresh_token:
    try:
        expiry = float(token_expiry)
    except (ValueError, TypeError):
        expiry = 0.0
    blob = json.dumps({
        "idToken": id_token,
        "refreshToken": refresh_token,
        "expiryTime": expiry,
        "tokenUserId": token_uid,
    })
    # Delete any existing item first so -U update cannot hit a poisoned ACL
    # from a different signing identity under the same service name.
    subprocess.run(
        ["security", "delete-generic-password", "-s", kc_service, "-a", kc_account],
        capture_output=True, text=True,
    )
    r = subprocess.run(
        ["security", "add-generic-password", "-s", kc_service, "-a", kc_account,
         "-w", blob, "-U"],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        print(f"Wrote token blob to Keychain ({kc_service}/{kc_account})")
    else:
        print(f"WARNING: could not write token blob to Keychain: {r.stderr.strip()}",
              file=sys.stderr)
else:
    print(f"No token values in dump — relying on existing Keychain item for {kc_service}")
PY

echo "Done — launch $TARGET and it boots signed-in (no web login)."
