#!/bin/bash
# omi-auth-seed.sh — replay a captured auth session into a test bundle.
#
# Writes the auth-state UserDefaults keys (isSignedIn, userEmail, userId,
# names, onboarding) captured by omi-auth-dump.sh into the target bundle's
# domain.  Auth tokens (idToken, refreshToken, expiry, tokenUserId) are shared
# via the login Keychain under a fixed service/account on ALL builds, so they
# are already available to the named bundle — no per-bundle seed needed.
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

# Token secrets live in the shared login Keychain — never write them to the
# target bundle's UserDefaults (that was the plaintext path this PR removed).
SKIP_KEYS="auth_idToken auth_refreshToken auth_tokenExpiry auth_tokenUserId"

python3 - "$TARGET" "$IN" "$SKIP_KEYS" <<'PY'
import json, subprocess, sys

target, inp = sys.argv[1], sys.argv[2]
skip = set(sys.argv[3].split())
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
PY

echo "Done — launch $TARGET and it boots signed-in (no web login)."
echo "Auth tokens are shared via the login Keychain — no per-bundle token seed needed."
