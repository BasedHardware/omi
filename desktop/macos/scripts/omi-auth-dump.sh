#!/bin/bash
# omi-auth-dump.sh — capture a signed-in dev bundle's auth session to JSON.
#
# Auth tokens (idToken, refreshToken, expiry, tokenUserId) live in the macOS
# Keychain on ALL builds (service "com.omi.desktop.firebase-rest-session",
# account "firebase-rest-tokens") — see AuthService.saveTokens(). The remaining
# auth-state keys (isSignedIn, userEmail, userId, names, onboarding) are in
# UserDefaults. This script reads BOTH so the captured session can be replayed
# into other test bundles with omi-auth-seed.sh, letting an agent skip the web
# OAuth login on every run.
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

# Keychain item that holds the JSON-encoded token blob (StoredAuthTokens).
KC_SERVICE="com.omi.desktop.firebase-rest-session"
KC_ACCOUNT="firebase-rest-tokens"

mkdir -p "$(dirname "$OUT")"

python3 - "$SRC" "$OUT" "${UD_KEYS[@]}" "$KC_SERVICE" "$KC_ACCOUNT" <<'PY'
import json, subprocess, sys

src, out = sys.argv[1], sys.argv[2]
ud_keys = sys.argv[3:-2]
kc_service, kc_account = sys.argv[-2], sys.argv[-1]

def defaults(*args):
    return subprocess.run(["defaults", *args], capture_output=True, text=True)

data = {}
for k in ud_keys:
    t = defaults("read-type", src, k)
    if t.returncode != 0:
        continue
    v = defaults("read", src, k)
    if v.returncode != 0:
        continue
    data[k] = {"type": t.stdout.strip().replace("Type is ", ""), "value": v.stdout.strip()}

# Read the token blob from the Keychain (shared login keychain, same
# service/account on every build).  `security find-generic-password -w` prints
# only the secret value to stdout.  Fall back to the legacy UserDefaults token
# keys for bundles that still have pre-migration tokens sitting there.
kc = subprocess.run(
    ["security", "find-generic-password", "-s", kc_service, "-a", kc_account, "-w"],
    capture_output=True, text=True,
)
if kc.returncode == 0 and kc.stdout.strip():
    payload = kc.stdout.strip()
    try:
        tokens = json.loads(payload)
        data["auth_idToken"] = {"type": "string", "value": tokens.get("idToken", "")}
        data["auth_refreshToken"] = {"type": "string", "value": tokens.get("refreshToken", "")}
        data["auth_tokenExpiry"] = {"type": "float", "value": str(tokens.get("expiryTime", 0))}
        data["auth_tokenUserId"] = {"type": "string", "value": tokens.get("tokenUserId", "")}
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
if "auth_idToken" not in data or not data["auth_idToken"].get("value"):
    sys.exit("WARNING: no auth_idToken found — is the source bundle signed in?")
PY
