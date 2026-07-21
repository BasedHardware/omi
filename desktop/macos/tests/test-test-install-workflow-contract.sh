#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_WORKFLOW="$SCRIPT_DIR/../.github/workflows/test-install.yml"
WORKFLOW="${2:-$DEFAULT_WORKFLOW}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

check_workflow() {
  python3 - "$WORKFLOW" <<'PY'
from pathlib import Path
import re
import shlex
import sys


def fail(message):
    raise SystemExit(f"FAIL: {message}")


workflow = Path(sys.argv[1])
lines = workflow.read_text().splitlines()
target_name = "Download DMG from GitHub Release"
step_matches = []
step_pattern = re.compile(r"^(?P<indent>\s*)-\s+name:\s*(?P<name>.*?)\s*(?:#.*)?$")

for index, line in enumerate(lines):
    match = step_pattern.match(line)
    if not match:
        continue
    name = match.group("name").strip().strip("\"'")
    if name == target_name:
        step_matches.append((index, len(match.group("indent"))))

if len(step_matches) != 1:
    fail(f"expected one {target_name!r} step, found {len(step_matches)}")

step_start, step_indent = step_matches[0]
step_end = len(lines)
next_step = re.compile(rf"^\s{{{step_indent}}}-\s+")
for index in range(step_start + 1, len(lines)):
    if next_step.match(lines[index]):
        step_end = index
        break

run_matches = []
run_pattern = re.compile(r"^(?P<indent>\s*)run:\s*\|\s*(?:#.*)?$")
for index in range(step_start + 1, step_end):
    match = run_pattern.match(lines[index])
    if match:
        run_matches.append((index, len(match.group("indent"))))

if len(run_matches) != 1:
    fail(f"installer step must have one literal run block, found {len(run_matches)}")

run_start, run_indent = run_matches[0]
run_lines = []
for line in lines[run_start + 1:step_end]:
    if line.strip() and len(line) - len(line.lstrip()) <= run_indent:
        break
    run_lines.append(line)

nonempty_indents = [len(line) - len(line.lstrip()) for line in run_lines if line.strip()]
if not nonempty_indents:
    fail("installer step run block is empty")
content_indent = min(nonempty_indents)
run_content = "\n".join(line[content_indent:] if line.strip() else "" for line in run_lines)


def other_step_run_content(target_name):
    other_steps = []
    for index, line in enumerate(lines):
        match = step_pattern.match(line)
        if match and match.group("name").strip().strip("\"'") == target_name:
            other_steps.append((index, len(match.group("indent"))))
    if len(other_steps) != 1:
        fail(f"expected one {target_name!r} step, found {len(other_steps)}")

    other_start, other_indent = other_steps[0]
    other_end = len(lines)
    other_next_step = re.compile(rf"^\s{{{other_indent}}}-\s+")
    for index in range(other_start + 1, len(lines)):
        if other_next_step.match(lines[index]):
            other_end = index
            break

    other_runs = []
    for index in range(other_start + 1, other_end):
        match = run_pattern.match(lines[index])
        if match:
            other_runs.append((index, len(match.group("indent"))))
    if len(other_runs) != 1:
        fail(f"{target_name!r} must have one literal run block, found {len(other_runs)}")

    other_run_start, other_run_indent = other_runs[0]
    other_run_lines = []
    for line in lines[other_run_start + 1:other_end]:
        if line.strip() and len(line) - len(line.lstrip()) <= other_run_indent:
            break
        other_run_lines.append(line)
    other_content_indents = [len(line) - len(line.lstrip()) for line in other_run_lines if line.strip()]
    if not other_content_indents:
        fail(f"{target_name!r} run block is empty")
    other_content_indent = min(other_content_indents)
    return "\n".join(line[other_content_indent:] if line.strip() else "" for line in other_run_lines)


run_content += "\n" + other_step_run_content("Mount DMG and Install")


def strip_shell_comment(line):
    quote = None
    escaped = False
    result = []
    for character in line:
        if escaped:
            result.append(character)
            escaped = False
            continue
        if character == "\\":
            result.append(character)
            escaped = True
            continue
        if quote:
            result.append(character)
            if character == quote:
                quote = None
            continue
        if character in "\"'":
            result.append(character)
            quote = character
        elif character == "#":
            break
        else:
            result.append(character)
    return "".join(result)


executable_lines = [strip_shell_comment(line).rstrip() for line in run_content.splitlines()]
executable_lines = [line for line in executable_lines if line.strip()]
executable_content = "\n".join(executable_lines)

logical_commands = []
pending = ""
for line in executable_lines:
    if line.endswith("\\") and not line.endswith("\\\\"):
        pending += f"{line[:-1].strip()} "
    else:
        logical_commands.append(f"{pending}{line.strip()}")
        pending = ""
if pending:
    fail("installer run block has an unterminated command continuation")


def token_segments(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";|&")
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)
    segments = []
    segment = []
    for token in tokens:
        if token and set(token) <= {";", "|", "&"}:
            if segment:
                segments.append(segment)
                segment = []
        else:
            segment.append(token)
    if segment:
        segments.append(segment)
    return segments


segments = [segment for command in logical_commands for segment in token_segments(command)]
assignment = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def executable_tokens(segment):
    index = 0
    while index < len(segment) and assignment.match(segment[index]):
        index += 1
    return segment[index:]


commands = [executable_tokens(segment) for segment in segments]
download_commands = [command for command in commands if command[:3] == ["gh", "release", "download"]]
if len(download_commands) != 1:
    fail(f"installer step must execute exactly one gh release download command, found {len(download_commands)}")

download = download_commands[0]
pattern_positions = [index for index, token in enumerate(download) if token == "--pattern"]
if len(pattern_positions) != 1 or any(token.startswith("--pattern=") for token in download):
    fail("installer download must use exactly one separate --pattern argument")
pattern_index = pattern_positions[0]
if pattern_index + 1 >= len(download) or download[pattern_index + 1] != "omi.dmg":
    fail("installer download pattern must be exactly lowercase omi.dmg")


def require_command(prefix, description):
    if not any(command[:len(prefix)] == prefix for command in commands):
        fail(f"installer run block missing executable {description}")


if not re.search(r'(?m)^DMG_PATH="\$DOWNLOAD_DIR/omi\.dmg"$', executable_content):
    fail("installer run block missing exact DMG_PATH assignment")
require_command(["xattr", "-d", "com.apple.quarantine", "$DMG_PATH"], "xattr dequarantine command")
if not re.search(
    r'DEVICE=\$\(hdiutil\s+attach\s+"\$DMG_PATH"\s+-nobrowse\s+-readonly\s+-mountpoint\s+"\$MOUNTPOINT"',
    executable_content,
):
    fail("installer run block missing exact device-capturing hdiutil attach command")
require_command(["hdiutil", "detach", "$DEVICE", "-quiet"], "device hdiutil detach command")
require_command(["trap", "cleanup", "EXIT"], "cleanup trap")
require_command(["ditto", "$MOUNTPOINT/Omi.app", "/Applications/Omi.app"], "mounted-app copy command")
if "/Volumes/Omi" in executable_content:
    fail("installer run block must not discover or detach a pre-existing /Volumes/Omi mount")
PY
}

check_workflow

if [[ "${1:-}" == "--check" ]]; then
  echo "test-install workflow exact-DMG contract passed"
  exit 0
fi

run_mutation() {
  local name="$1"
  local mutation="$2"
  local mutated_workflow
  mutated_workflow="$(mktemp "${TMPDIR:-/tmp}/test-install-${name}.XXXXXX")"
  trap 'rm -f "$mutated_workflow"' RETURN

  python3 - "$DEFAULT_WORKFLOW" "$mutated_workflow" "$mutation" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
mutation = sys.argv[3]
lines = source.read_text().splitlines(keepends=True)


def pattern_line_index():
    matches = [index for index, line in enumerate(lines) if '--pattern "omi.dmg"' in line]
    if len(matches) != 1:
        raise SystemExit(f"expected one canonical pattern line, found {len(matches)}")
    return matches[0]


if mutation == "comment-decoy-wildcard":
    index = pattern_line_index()
    lines[index:index + 1] = [
        '            # --pattern "omi.dmg" is the canonical download pattern.\n',
        lines[index].replace('"omi.dmg"', '"*.dmg"'),
    ]
elif mutation == "uppercase":
    index = pattern_line_index()
    lines[index] = lines[index].replace('--pattern "omi.dmg"', '--pattern "Omi.dmg"')
elif mutation == "beta":
    index = pattern_line_index()
    lines[index] = lines[index].replace('--pattern "omi.dmg"', '--pattern "omi-beta.dmg"')
elif mutation == "omitted":
    del lines[pattern_line_index()]
elif mutation == "duplicate":
    index = pattern_line_index()
    lines[index] = lines[index].replace('"omi.dmg"', '"omi.dmg" --pattern "other.dmg"')
elif mutation == "commented-command":
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith('gh release download')]
    if len(starts) != 1:
        raise SystemExit("canonical download command not found")
    start = starts[0]
    lines[start:start + 4] = [f"          # {line.lstrip()}" for line in lines[start:start + 4]]
else:
    raise SystemExit(f"unknown mutation: {mutation}")

destination.write_text(''.join(lines))
PY

  if bash "$SCRIPT_DIR/test-test-install-workflow-contract.sh" --check "$mutated_workflow"; then
    fail "mutation unexpectedly passed: $name"
  fi
}

run_mutation comment-decoy-wildcard comment-decoy-wildcard
run_mutation uppercase uppercase
run_mutation beta beta
run_mutation omitted omitted
run_mutation duplicate duplicate
run_mutation commented-command commented-command

echo "test-install workflow exact-DMG contract passed"
