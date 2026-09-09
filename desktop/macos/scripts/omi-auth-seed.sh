#!/bin/bash
# omi-auth-seed.sh — replay a captured auth session into a test bundle.
#
# Writes auth-state UserDefaults (isSignedIn, email, userId, names, onboarding)
# plus Firebase tokens into the target. Non-production targets persist tokens in
# the developer-secrets JSON file using the same scoped service name the app
# computes (`<base>.v2.team.<TeamID>.bundle.<bundleID>`; team-less identities
# use `adhoc.<bundleID>`). Production-family targets still seed UserDefaults
# token keys and clear a leftover CLI Keychain item so AuthService can migrate
# into the login keychain on launch.
#
# Why not write Keychain from this script for shipped bundles?
# The security(1) generic-password *add* path creates items with partition list
# `apple-tool:` only. TrustedApplication `-T /path/to/App.app` is not enough:
# the running app still gets the "wants to access key … in your keychain"
# password sheet.
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

TOKEN_SOURCE="file"
SECRETS_FILE="$(developer_secrets_file_for_bundle "$TARGET")"
if is_production_family_bundle "$TARGET"; then
  TOKEN_SOURCE="keychain"
  SECRETS_FILE=""
fi

python3 - "$TARGET" "$IN" "$TOKEN_SOURCE" "$SECRETS_FILE" "$KC_SERVICE" "$KC_ACCOUNT" <<'PY'
import json, os, subprocess, sys, tempfile

target, inp, token_source, secrets_file, kc_service, kc_account = sys.argv[1:7]
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

try:
    expiry_time = float(token_expiry or "0")
except ValueError:
    expiry_time = 0.0

payload = json.dumps(
    {
        "idToken": id_token,
        "refreshToken": refresh_token,
        "expiryTime": expiry_time,
        "tokenUserId": token_uid,
    },
    separators=(",", ":"),
)

if token_source == "keychain":
    # Remove any prior CLI-seeded Keychain item. Those carry partition list
    # apple-tool: only; leaving them makes the app prompt on SecItemCopyMatching
    # even with TrustedApplication -T grants. `security` (apple-tool:) can delete
    # without prompting; the app then migrates UserDefaults → Keychain on boot.
    subprocess.run(
        ["security", "delete-generic-password", "-s", kc_service, "-a", kc_account],
        capture_output=True, text=True,
    )
    print(f"Cleared Keychain item if present ({kc_service}/{kc_account})")
else:
    secrets_dir = os.path.dirname(secrets_file)
    os.makedirs(secrets_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(secrets_dir, 0o700)
    except OSError:
        pass
    obj = {}
    if os.path.isfile(secrets_file):
        try:
            with open(secrets_file, encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                obj = {
                    str(key): value if isinstance(value, str) else str(value)
                    for key, value in loaded.items()
                }
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            obj = {}
    obj[kc_service + "\0" + kc_account] = payload
    fd, tmp_path = tempfile.mkstemp(prefix=".developer-secrets.", dir=secrets_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, secrets_file)
        os.chmod(secrets_file, 0o600)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    print(f"Wrote developer secrets ({secrets_file})")

# Auth-state keys stay in UserDefaults. Token keys go there only for a
# production-family target, where AuthService migrates them into the login
# keychain on launch; a developer target already has them in its secrets file
# and must not keep a second plaintext copy in its defaults domain.
TOKEN_KEY_NAMES = {"auth_idToken", "auth_refreshToken", "auth_tokenExpiry", "auth_tokenUserId"}
TOKEN_KEYS = {
    "auth_idToken": id_token,
    "auth_refreshToken": refresh_token,
    "auth_tokenExpiry": str(expiry_time),
    "auth_tokenUserId": token_uid,
} if token_source == "keychain" else {}
SKIP_META = {"_keychainService", "_tokenSource", "_developerSecretsFile"}

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
    if k in TOKEN_KEY_NAMES or k in SKIP_META:
        continue
    typ, val = info["type"], info["value"]
    if typ == "boolean":
        val = "true" if val.strip().lower() in ("1", "true", "yes") else "false"
    subprocess.run(["defaults", "write", target, k, flag.get(typ, "-string"), val], check=True)
    n += 1

if token_source == "file":
    print(f"Seeded {n} keys into {target} (tokens via developer-secrets file)")
else:
    print(f"Seeded {n} keys into {target} (tokens via UserDefaults → Keychain migrate on launch)")
PY

echo "Done — launch $TARGET and it boots signed-in (no web login)."
