#!/usr/bin/env bash
# Hermetic contract tests for capture-ui-evidence.sh. No screen capture.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT="$MACOS_DIR/scripts/capture-ui-evidence.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$SCRIPT" ]] || fail "missing $SCRIPT"

# shellcheck source=../scripts/capture-ui-evidence.sh
source "$SCRIPT"

assert_fail_match() {
  local label="$1"
  local pattern="$2"
  shift 2
  local output status=0
  output="$("$@" 2>&1)" || status=$?
  if [[ "$status" -eq 0 ]]; then
    fail "$label: expected failure, got: $output"
  fi
  if ! grep -q -- "$pattern" <<<"$output"; then
    fail "$label: output did not match '$pattern': $output"
  fi
}

assert_eq() {
  local label="$1"
  local want="$2"
  local got="$3"
  [[ "$got" == "$want" ]] || fail "$label: expected '$want' got '$got'"
}

work="$(mktemp -d "${TMPDIR:-/tmp}/capture-ui-evidence.XXXXXX")"
cleanup() {
  rm -rf "$work"
}
trap cleanup EXIT

# Bad platform token.
assert_fail_match "bad platform" "desktop-macos" validate_filename "001-macos-settings.png"
assert_fail_match "other platform" "desktop-macos" validate_filename "001-desktop-windows-settings.png"

# Bad slug: uppercase, underscore, empty, too long, double hyphen.
assert_fail_match "uppercase slug" "lowercase-kebab" validate_slug "Settings"
assert_fail_match "underscore slug" "lowercase-kebab" validate_filename "001-desktop-macos-foo_bar.png"
assert_fail_match "double hyphen" "lowercase-kebab" validate_slug "foo--bar"
long_slug="$(python3 -c 'print("a" * 41)')"
assert_fail_match "long slug" "1-40" validate_slug "$long_slug"

# NNN is zero-padded from 001. Unpadded and 000 are rejected.
assert_eq "pad 1" "001" "$(format_ordinal 1)"
assert_eq "pad 7" "007" "$(format_ordinal 7)"
assert_eq "pad 12" "012" "$(format_ordinal 12)"
assert_eq "filename padding" "007-desktop-macos-chat-home.png" "$(evidence_filename 7 chat-home)"
assert_fail_match "unpadded ordinal" "001" validate_filename "7-desktop-macos-chat-home.png"
assert_fail_match "zero ordinal" "001" validate_filename "000-desktop-macos-chat-home.png"
assert_fail_match "ordinal 0" "1 to 999" format_ordinal 0
assert_fail_match "ordinal 1000" "1 to 999" format_ordinal 1000

slug40="$(python3 -c 'print("b" * 40)')"
assert_eq "40-char slug" "001-desktop-macos-${slug40}.png" "$(evidence_filename 1 "$slug40")"

# evidence.json merge preserves existing entries; same filename replaces in place.
manifest="$work/evidence.json"
update_evidence_json "$manifest" "002-desktop-macos-settings.png" "Settings"
update_evidence_json "$manifest" "001-desktop-macos-chat-home.png" "Chat home"
python3 - "$manifest" <<'PY'
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_bytes()
if not raw.endswith(b"\n"):
    raise SystemExit("evidence.json missing trailing newline")
text = raw.decode()
data = json.loads(text)
if text != json.dumps(data, indent=2, ensure_ascii=False) + "\n":
    raise SystemExit("evidence.json is not 2-space JSON with a trailing newline")
files = [item["file"] for item in data["images"]]
if files != ["002-desktop-macos-settings.png", "001-desktop-macos-chat-home.png"]:
    raise SystemExit(f"merge did not preserve order: {files}")
settings = data["images"][0]
if settings["description"] != "Settings" or settings["platform"] != "desktop-macos":
    raise SystemExit(f"existing entry changed: {settings}")
PY

update_evidence_json "$manifest" "001-desktop-macos-chat-home.png" "Chat home refreshed"
python3 - "$manifest" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if data["version"] != 1:
    raise SystemExit(f"version: {data['version']}")
files = [item["file"] for item in data["images"]]
if files != ["002-desktop-macos-settings.png", "001-desktop-macos-chat-home.png"]:
    raise SystemExit(f"replacement appended or dropped entries: {files}")
home = data["images"][1]
if home["description"] != "Chat home refreshed":
    raise SystemExit(f"description not replaced: {home}")
if home["captured_by"] != "agent" or home["source"] != "screencapture":
    raise SystemExit(f"metadata changed: {home}")
if data["images"][0]["description"] != "Settings":
    raise SystemExit("unrelated entry was rewritten")
PY

# End-to-end contract write uses a fake png. No screencapture.
out="$work/silo"
png="$work/fake.png"
printf 'fake-png-v1' >"$png"
commit_ui_evidence "$out" 4 "task-thread" "Task thread" "$png"
written="$out/004-desktop-macos-task-thread.png"
[[ -f "$written" ]] || fail "missing $written"
assert_eq "fake png bytes" "fake-png-v1" "$(cat "$written")"
python3 - "$out/evidence.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
raw = path.read_bytes()
text = raw.decode()
if not raw.endswith(b"\n"):
    raise SystemExit("missing trailing newline")
data = json.loads(text)
expected = {
    "version": 1,
    "images": [
        {
            "file": "004-desktop-macos-task-thread.png",
            "platform": "desktop-macos",
            "description": "Task thread",
            "captured_by": "agent",
            "source": "screencapture",
        }
    ],
}
if data != expected:
    raise SystemExit(f"manifest mismatch: {data}")
if text != json.dumps(expected, indent=2, ensure_ascii=False) + "\n":
    raise SystemExit("manifest formatting mismatch")
PY

printf 'fake-png-v2' >"$png"
commit_ui_evidence "$out" 4 "task-thread" "Task thread updated" "$png"
assert_eq "replaced png bytes" "fake-png-v2" "$(cat "$written")"
python3 - "$out/evidence.json" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
images = data["images"]
if len(images) != 1 or images[0]["description"] != "Task thread updated":
    raise SystemExit(f"same-file replacement failed: {images}")
if images[0]["file"] != "004-desktop-macos-task-thread.png":
    raise SystemExit(images)
PY

# Next ordinal skips invalid names and pads.
printf 'x' >"$out/notes.png"
printf 'x' >"$out/004-desktop-macos-task-thread.png"
assert_eq "next ordinal" "005" "$(next_ordinal "$out")"

# --out must stay inside the evidence silo. REPO_ROOT is the sourced script global.
saved_root="$REPO_ROOT"
REPO_ROOT="$work/repo"
mkdir -p "$REPO_ROOT/.agent-artifacts/ui-evidence/pr-12"
assert_eq "silo dir" "$REPO_ROOT/.agent-artifacts/ui-evidence/pr-12" "$(resolve_out_dir ".agent-artifacts/ui-evidence/pr-12")"
assert_eq "absolute silo" "$REPO_ROOT/.agent-artifacts/ui-evidence/pr-12" "$(resolve_out_dir "$REPO_ROOT/.agent-artifacts/ui-evidence/pr-12/")"
assert_fail_match "outside repo" "inside the repository" resolve_out_dir "/tmp/ui-evidence/pr-12"
assert_fail_match "bad dir slug" "lowercase-kebab-or-pr-number" resolve_out_dir ".agent-artifacts/ui-evidence/Bad_Name"
assert_fail_match "nested dir" "lowercase-kebab-or-pr-number" resolve_out_dir ".agent-artifacts/ui-evidence/pr-12/extra"
REPO_ROOT="$saved_root"

help_text="$(bash "$SCRIPT" --help)"
grep -q 'desktop-macos' <<<"$help_text" || fail "help does not mention desktop-macos"
grep -q 'Screen Recording' <<<"$(print_screen_recording_remediation 2>&1)" || fail "remediation missing Screen Recording"
grep -q 'System Settings → Privacy & Security → Screen Recording' <<<"$(print_screen_recording_remediation 2>&1)" || fail "remediation missing settings path"

echo "capture-ui-evidence contract tests passed"
