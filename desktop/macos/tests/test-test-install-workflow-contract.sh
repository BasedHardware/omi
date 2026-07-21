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
try:
    workflow_text = workflow.read_bytes().decode("utf-8")
except UnicodeDecodeError as error:
    fail(f"workflow must be UTF-8: {error}")
lines = workflow_text.splitlines(keepends=True)
target_name = "Download DMG from GitHub Release"


def without_line_ending(line):
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith(("\n", "\r")):
        return line[:-1]
    return line


def leading_spaces(line):
    return len(line) - len(line.lstrip(" "))


target_step_pattern = re.compile(r"^(?P<indent> *)- name: Download DMG from GitHub Release$")
step_matches = [
    (index, len(match.group("indent")))
    for index, line in enumerate(lines)
    if (match := target_step_pattern.match(without_line_ending(line)))
]
if len(step_matches) != 1:
    fail(f"expected one exact {target_name!r} step, found {len(step_matches)}")

step_start, step_indent = step_matches[0]
step_end = len(lines)
next_step_pattern = re.compile(rf"^{' ' * step_indent}- ")
for index in range(step_start + 1, len(lines)):
    if next_step_pattern.match(without_line_ending(lines[index])):
        step_end = index
        break

literal_run_pattern = re.compile(r"^(?P<indent> *)run: \|$")
run_matches = [
    (index, len(match.group("indent")))
    for index in range(step_start + 1, step_end)
    if (match := literal_run_pattern.match(without_line_ending(lines[index])))
]
if len(run_matches) != 1:
    fail(f"installer step must have exactly one literal `run: |` block, found {len(run_matches)}")

run_start, run_indent = run_matches[0]
run_lines = lines[run_start + 1:step_end]
nonempty_indents = [
    leading_spaces(without_line_ending(line))
    for line in run_lines
    if without_line_ending(line).strip(" ")
]
if not nonempty_indents:
    fail("installer literal run block is empty")
content_indent = min(nonempty_indents)
if content_indent <= run_indent:
    fail("installer literal run block is not indented beneath `run: |`")

normalized_run_lines = []
for line in run_lines:
    bare_line = without_line_ending(line)
    if bare_line.strip(" ") and not line.startswith(" " * content_indent):
        fail("installer literal run block has inconsistent YAML indentation")
    normalized_run_lines.append(line[min(leading_spaces(line), content_indent):])
run_content = "".join(normalized_run_lines)
if run_content.endswith("\r\n"):
    run_content = run_content[:-2] + "\n"
elif run_content.endswith("\r"):
    run_content = run_content[:-1] + "\n"
elif not run_content.endswith("\n"):
    run_content += "\n"

canonical_installer_run = '''echo "=== Downloading DMG ==="

# Get release tag from various sources
TAG="${{ github.event.inputs.release_tag }}"
if [ -z "$TAG" ] || [ "$TAG" = "latest" ]; then
  TAG="${{ github.event.client_payload.release_tag }}"
fi
if [ -z "$TAG" ] || [ "$TAG" = "latest" ]; then
  TAG=$(gh release list --repo BasedHardware/omi --limit 1 --json tagName --jq '.[0].tagName')
fi
echo "Testing release: $TAG"
echo "release_tag=$TAG" >> $GITHUB_OUTPUT

DOWNLOAD_DIR="$RUNNER_TEMP/omi-install-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
DMG_PATH="$DOWNLOAD_DIR/omi.dmg"
mkdir -p "$DOWNLOAD_DIR"

# Download only the canonical disk image, never another release asset.
gh release download "$TAG" \\
  --repo BasedHardware/omi \\
  --pattern "omi.dmg" \\
  --dir "$DOWNLOAD_DIR"
test -f "$DMG_PATH"
echo "dmg_path=$DMG_PATH" >> $GITHUB_OUTPUT

echo "## Release Under Test" >> $GITHUB_STEP_SUMMARY
echo "**Tag:** \\`$TAG\\`" >> $GITHUB_STEP_SUMMARY
echo "" >> $GITHUB_STEP_SUMMARY

'''
if run_content.encode("utf-8") != canonical_installer_run.encode("utf-8"):
    fail("installer literal run block differs from the admitted canonical block")


def other_step_run_content(target_name):
    step_pattern = re.compile(r"^(?P<indent>\s*)-\s+name:\s*(?P<name>.*?)\s*(?:#.*)?$")
    run_pattern = re.compile(r"^(?P<indent>\s*)run:\s*\|\s*(?:#.*)?$")
    other_steps = []
    for index, line in enumerate(lines):
        match = step_pattern.match(without_line_ending(line))
        if match and match.group("name").strip().strip("\"'") == target_name:
            other_steps.append((index, len(match.group("indent"))))
    if len(other_steps) != 1:
        fail(f"expected one {target_name!r} step, found {len(other_steps)}")

    other_start, other_indent = other_steps[0]
    other_end = len(lines)
    other_next_step = re.compile(rf"^\s{{{other_indent}}}-\s+")
    for index in range(other_start + 1, len(lines)):
        if other_next_step.match(without_line_ending(lines[index])):
            other_end = index
            break

    other_runs = []
    for index in range(other_start + 1, other_end):
        match = run_pattern.match(without_line_ending(lines[index]))
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
    return "\n".join(
        without_line_ending(line)[other_content_indent:] if line.strip() else "" for line in other_run_lines
    )


mount_content = other_step_run_content("Mount DMG and Install")


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


def logical_commands(content, description):
    executable_lines = [strip_shell_comment(line).rstrip() for line in content.splitlines()]
    executable_lines = [line for line in executable_lines if line.strip()]
    commands = []
    pending = ""
    for line in executable_lines:
        if line.endswith("\\") and not line.endswith("\\\\"):
            pending += f"{line[:-1].strip()} "
        else:
            commands.append(f"{pending}{line.strip()}")
            pending = ""
    if pending:
        fail(f"{description} has an unterminated command continuation")
    return commands


installer_commands = logical_commands(run_content, "installer run block")
canonical_installer_commands = [
    'echo "=== Downloading DMG ==="',
    'TAG="${{ github.event.inputs.release_tag }}"',
    'if [ -z "$TAG" ] || [ "$TAG" = "latest" ]; then',
    'TAG="${{ github.event.client_payload.release_tag }}"',
    'fi',
    'if [ -z "$TAG" ] || [ "$TAG" = "latest" ]; then',
    "TAG=$(gh release list --repo BasedHardware/omi --limit 1 --json tagName --jq '.[0].tagName')",
    'fi',
    'echo "Testing release: $TAG"',
    'echo "release_tag=$TAG" >> $GITHUB_OUTPUT',
    'DOWNLOAD_DIR="$RUNNER_TEMP/omi-install-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"',
    'DMG_PATH="$DOWNLOAD_DIR/omi.dmg"',
    'mkdir -p "$DOWNLOAD_DIR"',
    'gh release download "$TAG" --repo BasedHardware/omi --pattern "omi.dmg" --dir "$DOWNLOAD_DIR"',
    'test -f "$DMG_PATH"',
    'echo "dmg_path=$DMG_PATH" >> $GITHUB_OUTPUT',
    'echo "## Release Under Test" >> $GITHUB_STEP_SUMMARY',
    'echo "**Tag:** \\`$TAG\\`" >> $GITHUB_STEP_SUMMARY',
    'echo "" >> $GITHUB_STEP_SUMMARY',
]
if installer_commands != canonical_installer_commands:
    fail("installer run block does not match the admitted canonical command grammar")

# The admitted download production is deliberately direct and unwrapped.  Lex it
# independently so the argument contract remains explicit rather than relying on
# source-text coincidence.
download = shlex.split(installer_commands[13], posix=True)
expected_download = [
    "gh", "release", "download", "$TAG", "--repo", "BasedHardware/omi",
    "--pattern", "omi.dmg", "--dir", "$DOWNLOAD_DIR",
]
if download != expected_download:
    fail("installer download must be direct gh release download with one exact --pattern omi.dmg")


mount_executable_content = "\n".join(
    strip_shell_comment(line).rstrip() for line in mount_content.splitlines() if strip_shell_comment(line).strip()
)
mount_commands = [shlex.split(command, posix=True) for command in logical_commands(mount_content, "mount run block")]


def require_mount_command(prefix, description):
    if not any(command[:len(prefix)] == prefix for command in mount_commands):
        fail(f"mount run block missing executable {description}")


if not re.search(r'(?m)^DMG_PATH="\$\{\{ steps\.download\.outputs\.dmg_path \}\}"$', mount_executable_content):
    fail("mount run block missing exact DMG_PATH assignment")
require_mount_command(["xattr", "-d", "com.apple.quarantine", "$DMG_PATH"], "xattr dequarantine command")
if not re.search(
    r'DEVICE=\$\(hdiutil\s+attach\s+"\$DMG_PATH"\s+-nobrowse\s+-readonly\s+-mountpoint\s+"\$MOUNTPOINT"',
    mount_executable_content,
):
    fail("mount run block missing exact device-capturing hdiutil attach command")
require_mount_command(["hdiutil", "detach", "$DEVICE", "-quiet"], "device hdiutil detach command")
require_mount_command(["trap", "cleanup", "EXIT"], "cleanup trap")
require_mount_command(["ditto", "$MOUNTPOINT/Omi.app", "/Applications/Omi.app"], "mounted-app copy command")
if "/Volumes/Omi" in mount_executable_content:
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
  local expected="${3:-reject}"
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


def download_dir_line_index():
    matches = [index for index, line in enumerate(lines) if '--dir "$DOWNLOAD_DIR"' in line]
    if len(matches) != 1:
        raise SystemExit(f"expected one canonical download directory line, found {len(matches)}")
    return matches[0]


if mutation == "canonical":
    pass
elif mutation == "unrelated-yaml":
    matches = [index for index, line in enumerate(lines) if "timeout-minutes: 15" in line]
    if len(matches) != 1:
        raise SystemExit(f"expected one unrelated timeout line, found {len(matches)}")
    lines[matches[0]] = lines[matches[0]].replace("timeout-minutes: 15", "timeout-minutes: 16")
elif mutation == "comment-decoy-wildcard":
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
elif mutation == "long-equals":
    index = pattern_line_index()
    lines[index] = lines[index].replace('--pattern "omi.dmg"', '--pattern=omi.dmg')
elif mutation == "short-pattern":
    index = pattern_line_index()
    lines[index] = lines[index].replace('--pattern "omi.dmg"', '-p "omi.dmg"')
elif mutation == "short-pattern-concatenated":
    index = pattern_line_index()
    lines[index] = lines[index].replace('--pattern "omi.dmg"', '-pomi.dmg')
elif mutation == "mixed-long-short-patterns":
    index = pattern_line_index()
    lines[index] = lines[index].replace('--pattern "omi.dmg"', '--pattern "omi.dmg" -p "omi.dmg"')
elif mutation == "repeatable-short-wildcard":
    index = pattern_line_index()
    lines[index] = lines[index].replace('--pattern "omi.dmg"', '--pattern "omi.dmg" -p "*.dmg"')
elif mutation == "extra-direct-download":
    index = pattern_line_index()
    lines[index:index] = [
        '          gh release download "$TAG" --repo BasedHardware/omi --pattern "other.dmg" --dir "$DOWNLOAD_DIR"\n',
    ]
elif mutation == "extra-absolute-download":
    index = pattern_line_index()
    lines[index:index] = [
        '          /usr/local/bin/gh release download "$TAG" --repo BasedHardware/omi --pattern "other.dmg" --dir "$DOWNLOAD_DIR"\n',
    ]
elif mutation == "extra-command-wrapper-download":
    index = pattern_line_index()
    lines[index:index] = [
        '          command gh release download "$TAG" --repo BasedHardware/omi --pattern "other.dmg" --dir "$DOWNLOAD_DIR"\n',
    ]
elif mutation == "extra-env-wrapper-download":
    index = pattern_line_index()
    lines[index:index] = [
        '          env gh release download "$TAG" --repo BasedHardware/omi --pattern "other.dmg" --dir "$DOWNLOAD_DIR"\n',
    ]
elif mutation == "alias-gh":
    index = pattern_line_index()
    lines[index:index] = ["          alias gh='command gh'\n"]
elif mutation == "function-gh":
    index = pattern_line_index()
    lines[index:index] = ["          gh() { command gh \"$@\"; }\n"]
elif mutation == "function-keyword-gh":
    index = pattern_line_index()
    lines[index:index] = ["          function gh { command gh \"$@\"; }\n"]
elif mutation == "false-and-canonical":
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith('gh release download')]
    if len(starts) != 1:
        raise SystemExit("canonical download command not found")
    lines[starts[0]] = lines[starts[0]].replace('gh release download', 'false && gh release download')
elif mutation == "semicolon-before-canonical":
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith('gh release download')]
    if len(starts) != 1:
        raise SystemExit("canonical download command not found")
    lines[starts[0]] = lines[starts[0]].replace('gh release download', ':; gh release download')
elif mutation == "and-before-canonical":
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith('gh release download')]
    if len(starts) != 1:
        raise SystemExit("canonical download command not found")
    lines[starts[0]] = lines[starts[0]].replace('gh release download', ': && gh release download')
elif mutation == "or-before-canonical":
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith('gh release download')]
    if len(starts) != 1:
        raise SystemExit("canonical download command not found")
    lines[starts[0]] = lines[starts[0]].replace('gh release download', 'false || gh release download')
elif mutation == "pipeline-before-canonical":
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith('gh release download')]
    if len(starts) != 1:
        raise SystemExit("canonical download command not found")
    lines[starts[0]] = lines[starts[0]].replace('gh release download', ': | gh release download')
elif mutation == "subshell-canonical":
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith('gh release download')]
    if len(starts) != 1:
        raise SystemExit("canonical download command not found")
    lines[starts[0]] = lines[starts[0]].replace('gh release download', '( gh release download')
    lines[starts[0] + 3] = lines[starts[0] + 3].rstrip('\n') + ' )\n'
elif mutation in {"semicolon-after-canonical", "and-after-canonical", "or-after-canonical", "pipeline-after-canonical"}:
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith('gh release download')]
    if len(starts) != 1:
        raise SystemExit("canonical download command not found")
    suffixes = {
        "semicolon-after-canonical": "; :",
        "and-after-canonical": "&& :",
        "or-after-canonical": "|| :",
        "pipeline-after-canonical": "| cat",
    }
    end = starts[0] + 3
    lines[end] = lines[end].rstrip('\n') + f" {suffixes[mutation]}\n"
elif mutation == "benign-comment":
    index = pattern_line_index()
    lines[index:index] = ['          # This comment is intentionally inert.\n']
elif mutation == "no-whitespace-hash-literal":
    index = download_dir_line_index()
    lines[index] = lines[index].replace('--dir "$DOWNLOAD_DIR"', '--dir "$DOWNLOAD_DIR"#not-a-comment')
elif mutation == "no-whitespace-hash-parameter":
    index = download_dir_line_index()
    lines[index] = lines[index].replace('--dir "$DOWNLOAD_DIR"', '--dir "$DOWNLOAD_DIR"#${GH_TOKEN}')
elif mutation == "no-whitespace-hash-backtick":
    index = download_dir_line_index()
    lines[index] = lines[index].replace(
        '--dir "$DOWNLOAD_DIR"',
        '--dir "$DOWNLOAD_DIR"#`gh release download "$TAG" --repo BasedHardware/omi --pattern "*.dmg" --dir "$DOWNLOAD_DIR"`',
    )
elif mutation == "no-whitespace-hash-command-substitution":
    index = download_dir_line_index()
    lines[index] = lines[index].replace(
        '--dir "$DOWNLOAD_DIR"',
        '--dir "$DOWNLOAD_DIR"#$(gh release download "$TAG" --repo BasedHardware/omi --pattern "*.dmg" --dir "$DOWNLOAD_DIR")',
    )
else:
    raise SystemExit(f"unknown mutation: {mutation}")

destination.write_text(''.join(lines))
PY

  if bash "$SCRIPT_DIR/test-test-install-workflow-contract.sh" --check "$mutated_workflow"; then
    if [[ "$expected" == "reject" ]]; then
      fail "mutation unexpectedly passed: $name"
    fi
  elif [[ "$expected" == "accept" ]]; then
    fail "benign mutation unexpectedly failed: $name"
  fi
}

run_mutation comment-decoy-wildcard comment-decoy-wildcard
run_mutation uppercase uppercase
run_mutation beta beta
run_mutation omitted omitted
run_mutation duplicate duplicate
run_mutation commented-command commented-command
run_mutation canonical canonical accept
run_mutation unrelated-yaml unrelated-yaml accept
run_mutation long-equals long-equals
run_mutation short-pattern short-pattern
run_mutation short-pattern-concatenated short-pattern-concatenated
run_mutation mixed-long-short-patterns mixed-long-short-patterns
run_mutation repeatable-short-wildcard repeatable-short-wildcard
run_mutation extra-direct-download extra-direct-download
run_mutation extra-absolute-download extra-absolute-download
run_mutation extra-command-wrapper-download extra-command-wrapper-download
run_mutation extra-env-wrapper-download extra-env-wrapper-download
run_mutation alias-gh alias-gh
run_mutation function-gh function-gh
run_mutation function-keyword-gh function-keyword-gh
run_mutation false-and-canonical false-and-canonical
run_mutation semicolon-before-canonical semicolon-before-canonical
run_mutation and-before-canonical and-before-canonical
run_mutation or-before-canonical or-before-canonical
run_mutation pipeline-before-canonical pipeline-before-canonical
run_mutation subshell-canonical subshell-canonical
run_mutation semicolon-after-canonical semicolon-after-canonical
run_mutation and-after-canonical and-after-canonical
run_mutation or-after-canonical or-after-canonical
run_mutation pipeline-after-canonical pipeline-after-canonical
run_mutation no-whitespace-hash-command-substitution no-whitespace-hash-command-substitution
run_mutation no-whitespace-hash-backtick no-whitespace-hash-backtick
run_mutation no-whitespace-hash-parameter no-whitespace-hash-parameter
run_mutation no-whitespace-hash-literal no-whitespace-hash-literal
run_mutation benign-comment benign-comment

echo "test-install workflow exact-DMG contract passed"
