#!/bin/bash
# omi-auth-dump.sh — capture a signed-in dev bundle's auth session to JSON.
#
# Dev/named bundles store auth in UserDefaults (not Keychain) — see
# AuthService.restoreAuthState(). This script copies those keys verbatim so they
# can be replayed into other test bundles with omi-auth-seed.sh, letting an agent
# skip the web OAuth login on every run.
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
KEYS=(auth_isSignedIn auth_userEmail auth_userId auth_givenName auth_familyName \
      auth_idToken auth_refreshToken auth_tokenExpiry auth_tokenUserId hasCompletedOnboarding)

mkdir -p "$(dirname "$OUT")"

python3 - "$SRC" "$OUT" "${KEYS[@]}" <<'PY'
import json, subprocess, sys
src, out, keys = sys.argv[1], sys.argv[2], sys.argv[3:]

def defaults(*args):
    return subprocess.run(["defaults", *args], capture_output=True, text=True)

data = {}
for k in keys:
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
if "auth_idToken" not in data:
    sys.exit("WARNING: no auth_idToken found — is the source bundle signed in?")
PY
