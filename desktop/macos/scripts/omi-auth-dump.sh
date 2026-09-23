#!/bin/bash
# omi-auth-dump.sh — capture a signed-in bundle's auth session to JSON.
#
# Auth tokens (idToken, refreshToken, expiry, tokenUserId) live in
# DesktopKeychainStore: the login keychain on shipped production-family bundles
# (com.omi.computer-macos / com.omi.computer-macos.beta), and a JSON file under
# Application Support for every other bundle. Format of the scoped service name:
# <base>.v2.team.<TeamID>.bundle.<bundleID>
# The remaining auth-state keys (isSignedIn, userEmail, userId, names, onboarding)
# are in UserDefaults. This script reads BOTH so the captured session can be
# replayed into other test bundles with omi-auth-seed.sh, letting an agent skip
# the web OAuth login on every run.
#
# Developer-bundle dumps read the secrets file and work from a Background
# (non-Aqua) session. Production-family dumps still use `security find-generic-password`.
#
# It does NOT mint or refresh tokens — it copies whatever the source session has.
# The captured Firebase idToken expires (~1h); re-run this after signing in again.
#
# Usage: omi-auth-dump.sh [source-bundle-id] [out-file]
#   source-bundle-id  default: com.omi.desktop-dev   (the "Omi Dev" build).
#                     run.sh resolves this from OMI_AUTH_DUMP_SOURCE and falls
#                     back to the production app com.omi.computer-macos when
#                     the default source has no usable session; any installed
#                     Omi bundle works when invoked directly.
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

is_production_family_bundle() {
  case "$1" in
    com.omi.computer-macos|com.omi.computer-macos.beta) return 0 ;;
    *) return 1 ;;
  esac
}

application_support_root_for_bundle() {
  local bid="$1"
  local base="${HOME}/Library/Application Support"
  local prefix="com.omi.omi-"
  if [[ "$bid" == "$prefix"* ]]; then
    local suffix="${bid#"$prefix"}"
    if [[ -n "$suffix" && "$suffix" =~ ^[A-Za-z0-9.-]+$ ]]; then
      printf '%s/Omi Dev Bundles/%s\n' "$base" "$bid"
      return
    fi
  fi
  if [[ "$bid" == "com.omi.computer-macos.beta" ]]; then
    printf '%s/Omi Beta\n' "$base"
    return
  fi
  if [[ "${OMI_DESKTOP_LOCAL_PROFILE:-}" == "1" ]]; then
    printf '%s/%s\n' "$base" "${OMI_LOCAL_PROFILE_STORAGE_NAME:-Omi}"
    return
  fi
  printf '%s/Omi\n' "$base"
}

developer_secrets_file_for_bundle() {
  printf '%s/developer-secrets/%s.json\n' "$(application_support_root_for_bundle "$1")" "$1"
}

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

TOKEN_SOURCE="keychain"
SECRETS_FILE=""
if is_production_family_bundle "$SRC"; then
  TOKEN_SOURCE="keychain"
else
  TOKEN_SOURCE="file"
  SECRETS_FILE="$(developer_secrets_file_for_bundle "$SRC")"
fi

python3 - "$SRC" "$OUT" "$TOKEN_SOURCE" "$SECRETS_FILE" "$KC_SERVICE" "$KC_ACCOUNT" "${UD_KEYS[@]}" <<'PY'
import json, os, subprocess, sys

src, out, token_source, secrets_file, kc_service, kc_account = sys.argv[1:7]
ud_keys = sys.argv[7:]

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

def read_developer_secrets(path, service):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            obj = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    payload = obj.get(service + "\0" + kc_account)
    if isinstance(payload, str) and payload.strip():
        return payload
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

# Production-family sources read the team+bundle scoped v2 keychain item and
# never query the unscoped legacy service. Developer sources read the JSON file
# and never call `security`.
if token_source == "file":
    payload = read_developer_secrets(secrets_file, kc_service)
    data["_tokenSource"] = {"type": "string", "value": "developer-secrets"}
    if secrets_file:
        data["_developerSecretsFile"] = {"type": "string", "value": secrets_file}
else:
    payload = read_keychain(kc_service)
    data["_tokenSource"] = {"type": "string", "value": "keychain"}

if payload:
    try:
        tokens = json.loads(payload)
        # Validate tokenUserId against the UserDefaults auth_userId to avoid
        # seeding signed-in state for one user with tokens belonging to a
        # different user.
        kc_uid = tokens.get("tokenUserId", "")
        ud_uid = data.get("auth_userId", {}).get("value", "")
        if ud_uid and kc_uid != ud_uid:
            print(f"WARNING: tokenUserId ({kc_uid}) does not match "
                  f"UserDefaults auth_userId ({ud_uid}) — falling back to "
                  f"UserDefaults token keys.", file=sys.stderr)
        else:
            data["auth_idToken"] = {"type": "string", "value": tokens.get("idToken", "")}
            data["auth_refreshToken"] = {"type": "string", "value": tokens.get("refreshToken", "")}
            data["auth_tokenExpiry"] = {"type": "float", "value": str(tokens.get("expiryTime", 0))}
            data["auth_tokenUserId"] = {"type": "string", "value": kc_uid}
            data["_keychainService"] = {"type": "string", "value": kc_service}
    except (json.JSONDecodeError, KeyError, TypeError):
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
print(f"  token_source={token_source} service={kc_service}")
if token_source == "file":
    print(f"  developer_secrets_file={secrets_file}")
if "auth_idToken" not in data or not data["auth_idToken"].get("value"):
    sys.exit("WARNING: no auth_idToken found — is the source bundle signed in?")
PY
