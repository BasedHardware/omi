#!/usr/bin/env bash
# Contract: automation token readers must prefer Darwin user temp (NSTemporaryDirectory)
# over TMPDIR/ /tmp so launchd / Actions / Multica TMPDIR overrides cannot 401 the bridge.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB="$MACOS_DIR/scripts/automation_token_lib.py"
PATH_SH="$MACOS_DIR/scripts/automation-token-path.sh"
RUN_SH="$MACOS_DIR/run.sh"
HARNESS="$MACOS_DIR/scripts/omi-harness"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$LIB" ]] || fail "missing $LIB"
[[ -f "$PATH_SH" ]] || fail "missing $PATH_SH"

# shellcheck source=../scripts/automation-token-path.sh
source "$PATH_SH"

DARWIN_TMP="$(getconf DARWIN_USER_TEMP_DIR)"
[[ -n "$DARWIN_TMP" ]] || fail "getconf DARWIN_USER_TEMP_DIR returned empty"

PORT=59847
EXPECTED="${DARWIN_TMP%/}/omi-automation-${PORT}.token"
GOT="$(omi_automation_token_file "$PORT")"
[[ "$GOT" == "$EXPECTED" ]] || fail "shell resolver expected $EXPECTED got $GOT"

# Explicit override still wins.
GOT="$(OMI_AUTOMATION_TOKEN_FILE=/tmp/custom.token omi_automation_token_file "$PORT")"
[[ "$GOT" == "/tmp/custom.token" ]] || fail "explicit OMI_AUTOMATION_TOKEN_FILE ignored"

python3 - "$LIB" "$PORT" "$DARWIN_TMP" <<'PY'
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

lib_path = Path(sys.argv[1])
port = int(sys.argv[2])
darwin = Path(sys.argv[3])

spec = importlib.util.spec_from_file_location("automation_token_lib", lib_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

# With a divergent TMPDIR, Darwin path must still be preferred.
os.environ.pop("OMI_AUTOMATION_TOKEN", None)
os.environ.pop("OMI_AUTOMATION_TOKEN_FILE", None)
os.environ["TMPDIR"] = "/tmp"
candidates = module.automation_token_file_candidates(port)
assert candidates[0] == darwin / f"omi-automation-{port}.token", candidates
assert any(path.name == f"omi-automation-{port}.token" and path.parent == Path("/tmp") for path in candidates), candidates

with tempfile.TemporaryDirectory() as fake_darwin:
    fake = Path(fake_darwin)
    token_path = fake / f"omi-automation-{port}.token"
    token_path.write_text("omi_auto_testtoken1234567890ab", encoding="utf-8")
    # Monkeypatch darwin lookup to the fake dir while TMPDIR remains /tmp (empty).
    module.darwin_user_temp_dir = lambda: fake  # type: ignore[method-assign]
    assert module.automation_token(port) == "omi_auto_testtoken1234567890ab"

    os.environ["OMI_AUTOMATION_TOKEN"] = "env-token"
    assert module.automation_token(port) == "env-token"
    del os.environ["OMI_AUTOMATION_TOKEN"]
PY

grep -Fq 'automation_token_missing' "$HARNESS" || fail "omi-harness must fail loud on missing token"
grep -Fq 'automation_token_lib' "$HARNESS" || fail "omi-harness must use shared automation_token_lib"
grep -Fq 'OMI_AUTOMATION_TOKEN_FILE' "$RUN_SH" || fail "run.sh must forward OMI_AUTOMATION_TOKEN_FILE through open --env when set"

echo "automation token path contract tests passed"
