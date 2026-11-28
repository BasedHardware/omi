#!/bin/bash
# Writes a clean copy of the committed tree (no git history, no files marked export-ignore in
# .gitattributes) to <out>/<name>, then refuses if anything secret or personal slipped in.
# Usage: Tools/export-clean.sh <repo> <out-dir> <name>
#   e.g. Tools/export-clean.sh . ~/CODING/omi-export app-ios-native
set -euo pipefail
repo=$(cd "$1" && pwd); out=$2; name=$3
dest="$out/$name"
rm -rf "$dest"; mkdir -p "$dest"
git -C "$repo" archive --format=tar HEAD | tar -x -C "$dest"

fail=0
check() { # pattern, description (this script itself is skipped: it holds the patterns)
    if hits=$(grep -rIlE --exclude=export-clean.sh "$1" "$dest" 2>/dev/null) && [ -n "$hits" ]; then
        echo "BLOCKED: $2"; echo "$hits" | sed 's/^/  /'; fail=1
    fi
}
check 'sk-or-v1-[A-Za-z0-9]{20}|sk-[A-Za-z0-9]{32}|-----BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20}' "API keys or private keys"
# Google API keys; the local emulator config carries a fake one (AIzaSyDEMOOMILOCAL...), which is fine.
if keys=$(grep -rIoE --exclude=export-clean.sh 'AIza[0-9A-Za-z_-]{30,}' "$dest" | grep -v 'AIzaSyDEMOOMILOCAL') && [ -n "$keys" ]; then
    echo "BLOCKED: Google API keys"; echo "$keys" | sed 's/^/  /'; fail=1
fi
check '/Users/leon|florianmoller|K5KT5FXP8J|192\.168\.1\.[0-9]+:' "personal paths, ids or LAN addresses"
for f in GoogleService-Info-Prod.plist google-services.json Secrets.xcconfig local.properties; do
    if found=$(find "$dest" -name "$f" -not -path '*/src/local/*') && [ -n "$found" ]; then
        echo "BLOCKED: $f is in the export"; echo "$found" | sed 's/^/  /'; fail=1
    fi
done
if [ $fail -ne 0 ]; then echo "Export left at $dest for inspection; fix the repo and run again."; exit 1; fi
echo "Clean export: $dest ($(find "$dest" -type f | wc -l | tr -d ' ') files)"
