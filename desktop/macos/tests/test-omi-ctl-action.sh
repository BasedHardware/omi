#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OMI_CTL="$SCRIPT_DIR/../scripts/omi-ctl"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-ctl-action.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/bin"

# Capture the actual request body at the transport boundary without a live app.
cat > "$TMP_ROOT/bin/curl" <<'SH'
#!/usr/bin/env bash
while [ "$#" -gt 0 ]; do
  if [ "$1" = -d ]; then
    printf '%s' "$2" > "$OMI_CTL_REQUEST_FILE"
    printf '{"ok":true}\n'
    exit 0
  fi
  shift
done
exit 1
SH
chmod +x "$TMP_ROOT/bin/curl"

PATH="$TMP_ROOT/bin:$PATH" OMI_AUTOMATION_TOKEN=test-token \
  OMI_CTL_REQUEST_FILE="$TMP_ROOT/request.json" \
  python3 - "$OMI_CTL" "$TMP_ROOT/request.json" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

ctl, request = sys.argv[1:]
request = Path(request)

def run(*args):
    return subprocess.run([ctl, "action", *args], capture_output=True, text=True)

query = 'QA "quoted" search\\path\n第二行\tvalue=a=b'
result = run("set_conversations_search", "query=" + query, "empty=")
assert result.returncode == 0, result.stderr
assert json.loads(request.read_text()) == {
    "name": "set_conversations_search", "params": {"query": query, "empty": ""}
}
result = run("permissions_snapshot")
assert result.returncode == 0, result.stderr
assert json.loads(request.read_text()) == {"name": "permissions_snapshot"}
for argument in ("missing-separator", "=missing-key"):
    request.unlink(missing_ok=True)
    result = run("set_conversations_search", argument)
    assert result.returncode != 0
    assert "key=value" in result.stderr
    assert not request.exists(), "invalid arguments must fail before transport"
print("omi-ctl action request encoding tests passed")
PY
