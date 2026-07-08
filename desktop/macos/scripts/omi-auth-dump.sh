#!/bin/bash
# omi-auth-dump.sh — capture a signed-in dev bundle's auth session to JSON.
#
# Auth tokens (idToken, refreshToken, expiry, tokenUserId) live in the macOS
# Keychain on ALL builds under a Team+bundle scoped service name derived from
# "com.omi.desktop.firebase-rest-session" (see DesktopKeychainStore.scopedService).
# Format: <base>.v2.team.<TeamID>.bundle.<bundleID>
# The remaining auth-state keys (isSignedIn, userEmail, userId, names, onboarding)
# are in UserDefaults. This script reads BOTH so the captured session can be
# replayed into other test bundles with omi-auth-seed.sh, letting an agent skip
# the web OAuth login on every run.
#
# It does NOT mint or refresh tokens — it copies whatever the source session has.
# The captured Firebase idToken expires (~1h); re-run this after signing in again.
#
# Usage: omi-auth-dump.sh [source-bundle-id] [out-file]
#   source-bundle-id  default: com.omi.desktop-dev   (the "Omi Dev" build)
#   out-file          default: desktop/tmp/desktop-auth.json (gitignored)
set -euo pipefail

SRC="${1:-com.omi.desktop-dev}"
OUT="${2:-$(cd "$(dirname "$0")/.." && pwd)/tmp/desktop-auth.json}"

# Auth-state keys that remain in UserDefaults (not token secrets).
UD_KEYS=(auth_isSignedIn auth_userEmail auth_userId auth_givenName auth_familyName \
         hasCompletedOnboarding)

# Keychain base service/account. The actual service is team+bundle scoped at runtime.
KC_SERVICE_BASE="com.omi.desktop.firebase-rest-session"
KC_ACCOUNT="firebase-rest-tokens"

mkdir -p "$(dirname "$OUT")"

# Resolve an installed .app path for the source bundle so we can read its Team ID.
resolve_app_path() {
  local bid="$1"
  local path
  path="$(mdfind "kMDItemCFBundleIdentifier == '$bid'" 2>/dev/null | head -1 || true)"
  if [ -n "$path" ] && [ -d "$path" ]; then
    printf '%s\n' "$path"
    return 0
  fi
  # Common install locations for Omi Dev / named bundles.
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

APP_PATH="$(resolve_app_path "$SRC" || true)"
TEAM_ID=""
if [ -n "$APP_PATH" ]; then
  TEAM_ID="$(codesign -dv --verbose=4 "$APP_PATH" 2>&1 | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
fi
if [ -z "$TEAM_ID" ] || [ "$TEAM_ID" = "not set" ]; then
  TEAM_ID="adhoc.${SRC}"
fi
KC_SERVICE="${KC_SERVICE_BASE}.v2.team.${TEAM_ID}.bundle.${SRC}"

python3 - "$SRC" "$OUT" "${UD_KEYS[@]}" "$KC_SERVICE" "$KC_SERVICE_BASE" "$KC_ACCOUNT" <<'PY'
import json, subprocess, sys

src, out = sys.argv[1], sys.argv[2]
ud_keys = sys.argv[3:-3]
kc_service, kc_service_legacy, kc_account = sys.argv[-3], sys.argv[-2], sys.argv[-1]

def defaults(*args):
    return subprocess.run(["defaults", *args], capture_output=True, text=True)

def read_keychain(service):
    kc = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", kc_account, "-w"],
        capture_output=True, text=True,
    )
    if kc.returncode == 0 and kc.stdout.strip():
        return kc.stdout.strip()
    return None

data = {}
for k in ud_keys:
    t = defaults("read-type", src, k)
    if t.returncode != 0:
        continue
    v = defaults("read", src, k)
    if v.returncode != 0:
        continue
    data[k] = {"type": t.stdout.strip().replace("Type is ", ""), "value": v.stdout.strip()}

# Prefer the team+bundle scoped v2 item. Optionally try the unscoped legacy name
# for pre-migration sessions — `security` may itself prompt if that ACL is
# poisoned; Prefer Always Allow once, or delete the poisoned item. The app never
# queries the legacy name (that is what caused the Beta password dialog).
payload = read_keychain(kc_service) or read_keychain(kc_service_legacy)
if payload:
    try:
        tokens = json.loads(payload)
        # Validate tokenUserId against the UserDefaults auth_userId to avoid
        # seeding signed-in state for one user with Keychain tokens belonging
        # to a different user.
        kc_uid = tokens.get("tokenUserId", "")
        ud_uid = data.get("auth_userId", {}).get("value", "")
        if ud_uid and kc_uid != ud_uid:
            print(f"WARNING: Keychain tokenUserId ({kc_uid}) does not match "
                  f"UserDefaults auth_userId ({ud_uid}) — falling back to "
                  f"UserDefaults token keys.", file=sys.stderr)
        else:
            data["auth_idToken"] = {"type": "string", "value": tokens.get("idToken", "")}
            data["auth_refreshToken"] = {"type": "string", "value": tokens.get("refreshToken", "")}
            data["auth_tokenExpiry"] = {"type": "float", "value": str(tokens.get("expiryTime", 0))}
            data["auth_tokenUserId"] = {"type": "string", "value": kc_uid}
            data["_keychainService"] = {"type": "string", "value": kc_service}
    except (json.JSONDecodeError, KeyError):
        pass  # fall through to UserDefaults below

# Legacy fallback: pre-migration bundles may still have token keys in UserDefaults.
for k in ("auth_idToken", "auth_refreshToken", "auth_tokenExpiry", "auth_tokenUserId"):
    if k in data:
        continue
    t = defaults("read-type", src, k)
    if t.returncode != 0:
        continue
    v = defaults("read", src, k)
    if v.returncode != 0:
        continue
    data[k] = {"type": t.stdout.strip().replace("Type is ", ""), "value": v.stdout.strip()}

with open(out, "w") as f:
    json.dump(data, f, indent=2)

print(f"Dumped {len(data)} keys from {src} -> {out}")
print(f"  signed_in={data.get('auth_isSignedIn', {}).get('value')} "
      f"email={data.get('auth_userEmail', {}).get('value')}")
print(f"  keychain_service={kc_service}")
if "auth_idToken" not in data or not data["auth_idToken"].get("value"):
    sys.exit("WARNING: no auth_idToken found — is the source bundle signed in?")
PY
