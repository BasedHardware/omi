#!/bin/bash
# omi-auth-seed.sh — replay a captured auth session into a test bundle.
#
# Writes auth-state UserDefaults (isSignedIn, email, userId, names, onboarding)
# plus Firebase token keys into the target bundle's domain. On first launch,
# AuthService.storedTokens() migrates those UserDefaults tokens into the
# team+bundle scoped Keychain item via SecItemAdd — which stamps the correct
# teamid: partition so the app can read them without a login-keychain prompt.
#
# Why not write Keychain from this script?
# The security(1) generic-password *add* path creates items with partition list
# `apple-tool:` only. TrustedApplication `-T /path/to/App.app` is not enough:
# the running app still gets the "wants to access key … in your keychain"
# password sheet. Deleting any prior CLI-written item and seeding UserDefaults
# avoids that path entirely for named-bundle / agent launches.
#
# Run this BEFORE launching the bundle (UserDefaults is read at startup).
#
# Usage: omi-auth-seed.sh <target-bundle-id> [in-file] [app-path]
#   target-bundle-id  e.g. com.omi.omi-fix-rewind  (a named test bundle)
#   in-file           default: desktop/tmp/desktop-auth.json
#   app-path          optional; also via OMI_AUTH_SEED_APP_PATH (used for Team ID)
set -euo pipefail

TARGET="${1:?usage: omi-auth-seed.sh <target-bundle-id> [in-file] [app-path]}"
IN="${2:-$(cd "$(dirname "$0")/.." && pwd)/tmp/desktop-auth.json}"
APP_PATH_ARG="${3:-${OMI_AUTH_SEED_APP_PATH:-}}"

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

if [ -n "$APP_PATH_ARG" ]; then
  APP_PATH="$APP_PATH_ARG"
else
  APP_PATH="$(resolve_app_path "$TARGET" || true)"
fi

TEAM_ID=""
if [ -n "${APP_PATH:-}" ] && [ -d "$APP_PATH" ]; then
  FOUND_BID="$(defaults read "$APP_PATH/Contents/Info" CFBundleIdentifier 2>/dev/null || true)"
  if [ -n "$FOUND_BID" ] && [ "$FOUND_BID" != "$TARGET" ]; then
    echo "ERROR: app at $APP_PATH has bundle id '$FOUND_BID', expected '$TARGET'." >&2
    exit 1
  fi
  TEAM_ID="$(codesign -dv --verbose=4 "$APP_PATH" 2>&1 | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
fi
if [ -z "$TEAM_ID" ] || [ "$TEAM_ID" = "not set" ]; then
  TEAM_ID="adhoc.${TARGET}"
fi
KC_SERVICE="${KC_SERVICE_BASE}.v2.team.${TEAM_ID}.bundle.${TARGET}"

python3 - "$TARGET" "$IN" "$KC_SERVICE" "$KC_ACCOUNT" <<'PY'
import json, subprocess, sys

target, inp = sys.argv[1], sys.argv[2]
kc_service, kc_account = sys.argv[3], sys.argv[4]
data = json.load(open(inp))

id_token = data.get("auth_idToken", {}).get("value", "")
refresh_token = data.get("auth_refreshToken", {}).get("value", "")
token_expiry = data.get("auth_tokenExpiry", {}).get("value", "0")
token_uid = data.get("auth_tokenUserId", {}).get("value", "")

if not id_token or not refresh_token:
    print("ERROR: dump has no auth_idToken/auth_refreshToken — refusing to seed "
          "signed-in state without credentials. Re-run omi-auth-dump.sh "
          "from a signed-in source bundle.", file=sys.stderr)
    sys.exit(1)

# Remove any prior CLI-seeded Keychain item. Those carry partition list
# apple-tool: only; leaving them makes the app prompt on SecItemCopyMatching
# even with TrustedApplication -T grants. `security` (apple-tool:) can delete
# without prompting; the app then migrates UserDefaults → Keychain on boot.
subprocess.run(
    ["security", "delete-generic-password", "-s", kc_service, "-a", kc_account],
    capture_output=True, text=True,
)
print(f"Cleared Keychain item if present ({kc_service}/{kc_account})")

# Token keys are seeded into UserDefaults for one-shot migration by AuthService.
# Do not CLI-add a generic-password item — that recreates the apple-tool:
# partition prompt path.
TOKEN_KEYS = {
    "auth_idToken": id_token,
    "auth_refreshToken": refresh_token,
    "auth_tokenExpiry": str(token_expiry),
    "auth_tokenUserId": token_uid,
}
SKIP_META = {"_keychainService"}

flag = {"boolean": "-bool", "string": "-string", "integer": "-int",
        "float": "-float", "date": "-date", "data": "-data"}

n = 0
for key, val in TOKEN_KEYS.items():
    if key == "auth_tokenExpiry":
        # AuthService reads this as Double via UserDefaults.double(forKey:)
        subprocess.run(
            ["defaults", "write", target, key, "-float", val or "0"],
            check=True,
        )
    else:
        subprocess.run(
            ["defaults", "write", target, key, "-string", val],
            check=True,
        )
    n += 1

for k, info in data.items():
    if k in TOKEN_KEYS or k in SKIP_META:
        continue
    typ, val = info["type"], info["value"]
    if typ == "boolean":
        val = "true" if val.strip().lower() in ("1", "true", "yes") else "false"
    subprocess.run(["defaults", "write", target, k, flag.get(typ, "-string"), val], check=True)
    n += 1

print(f"Seeded {n} keys into {target} (tokens via UserDefaults → Keychain migrate on launch)")
PY

echo "Done — launch $TARGET and it boots signed-in (no web login)."
