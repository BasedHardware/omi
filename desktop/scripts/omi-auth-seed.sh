#!/bin/bash
# omi-auth-seed.sh — replay a captured auth session into a test bundle.
#
# Writes the auth_* UserDefaults keys (and hasCompletedOnboarding) captured by
# omi-auth-dump.sh into the target bundle's domain. On next launch the app's
# restoreAuthState() picks them up and boots already-signed-in — no browser.
#
# Run this BEFORE launching the bundle (UserDefaults is read at startup).
#
# Usage: omi-auth-seed.sh <target-bundle-id> [in-file]
#   target-bundle-id  e.g. com.omi.omi-fix-rewind  (a named test bundle)
#   in-file           default: desktop/tmp/desktop-auth.json
set -euo pipefail

TARGET="${1:?usage: omi-auth-seed.sh <target-bundle-id> [in-file]}"
IN="${2:-$(cd "$(dirname "$0")/.." && pwd)/tmp/desktop-auth.json}"

[ -f "$IN" ] || { echo "No auth file at $IN — run omi-auth-dump.sh first." >&2; exit 1; }

python3 - "$TARGET" "$IN" <<'PY'
import json, subprocess, sys
target, inp = sys.argv[1], sys.argv[2]
data = json.load(open(inp))

flag = {"boolean": "-bool", "string": "-string", "integer": "-int",
        "float": "-float", "date": "-date", "data": "-data"}

n = 0
for k, info in data.items():
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
