#!/bin/bash
# omi-auth-seed.sh — replay a captured auth session into a test bundle.
#
# Writes the auth-state UserDefaults keys (isSignedIn, userEmail, userId,
# names, onboarding) captured by omi-auth-dump.sh into the target bundle's
# domain.  Auth tokens (idToken, refreshToken, expiry, tokenUserId) are shared
# via the login Keychain under a fixed service/account on ALL builds, so they
# are already available to the named bundle — no per-bundle seed needed.
#
# If the dump captured tokens from UserDefaults (pre-migration source bundle
# that has not yet migrated to Keychain), those token values are written into
# the shared Keychain item so the target bundle can read them on launch.
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

# Keychain item that holds the JSON-encoded token blob (StoredAuthTokens).
KC_SERVICE="com.omi.desktop.firebase-rest-session"
KC_ACCOUNT="firebase-rest-tokens"

# Token secrets are never written to the target bundle's UserDefaults — that
# was the plaintext path this PR removed.  If tokens are present in the dump
# (from a pre-migration source), they are written to the shared Keychain.
SKIP_KEYS="auth_idToken auth_refreshToken auth_tokenExpiry auth_tokenUserId"

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

# If the dump captured token values (from a pre-migration source bundle that
# still had them in UserDefaults), write them into the shared Keychain item so
# the target bundle can read them on launch.  On post-migration bundles the
# Keychain item already exists and this is a no-op (same service/account).
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
PY

echo "Done — launch $TARGET and it boots signed-in (no web login)."
