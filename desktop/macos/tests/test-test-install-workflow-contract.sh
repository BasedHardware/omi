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


if re.search(r"(?m)(?:^|[ \t:\[\]{},])(?:&|\*)[A-Za-z_][A-Za-z0-9_-]*", workflow_text):
    fail("workflow must not use YAML anchors or aliases")


def step_end_after(step_start, step_indent):
    next_step_pattern = re.compile(rf"^{' ' * step_indent}- ")
    for index in range(step_start + 1, len(lines)):
        if next_step_pattern.match(without_line_ending(lines[index])):
            return index
    return len(lines)


def exact_named_steps(name):
    pattern = re.compile(rf"^(?P<indent> *)- name: {re.escape(name)}$")
    return [
        (index, len(match.group("indent")))
        for index, line in enumerate(lines)
        if (match := pattern.match(without_line_ending(line)))
    ]


# The name itself is part of the identity contract.  A quoted or otherwise
# noncanonical spelling is not an alternate representation: it is a decoy.
name_mentions = [
    (index, without_line_ending(line))
    for index, line in enumerate(lines)
    if re.match(r"^ *-\s+name:", without_line_ending(line)) and target_name in without_line_ending(line)
]
for _, line in name_mentions:
    if line != f"      - name: {target_name}":
        fail("installer step name must use the one exact unquoted canonical spelling")

step_matches = exact_named_steps(target_name)
if len(step_matches) != 1:
    fail(f"expected one exact {target_name!r} step, found {len(step_matches)}")

step_start, step_indent = step_matches[0]
step_end = step_end_after(step_start, step_indent)
field_indent = step_indent + 2
if without_line_ending(lines[step_start]) != f"{' ' * step_indent}- name: {target_name}":
    fail("installer step name is not the exact canonical YAML line")

id_pattern = re.compile(r"^(?P<indent> *)id:\s*(?P<value>.*?)$")
download_ids = []
for index, line in enumerate(lines):
    match = id_pattern.match(without_line_ending(line))
    if match and match.group("value").strip().strip("\"'") == "download":
        download_ids.append((index, len(match.group("indent")), without_line_ending(line)))
if len(download_ids) != 1:
    fail(f"expected one executable id: download, found {len(download_ids)}")
id_index, id_indent, id_line = download_ids[0]
if not (step_start < id_index < step_end) or id_indent != field_indent or id_line != f"{' ' * field_indent}id: download":
    fail("canonical installer step must own the exact literal id: download")

run_key_pattern = re.compile(rf"^{' ' * field_indent}run:")
run_keys = [index for index in range(step_start + 1, step_end) if run_key_pattern.match(without_line_ending(lines[index]))]
if len(run_keys) != 1:
    fail(f"installer step must have exactly one run key, found {len(run_keys)}")
run_start = run_keys[0]
run_line = without_line_ending(lines[run_start])
if run_line != f"{' ' * field_indent}run: |":
    fail("installer step must use the exact literal run: | indicator without chomping or aliases")
run_indent = field_indent


def literal_body_end(run_start, run_indent, limit):
    for index in range(run_start + 1, limit):
        bare_line = without_line_ending(lines[index])
        if bare_line.strip(" ") and leading_spaces(bare_line) <= run_indent:
            return index
    return limit


run_end = literal_body_end(run_start, run_indent, step_end)
if run_end != step_end:
    fail("installer literal run block must occupy the rest of its step")

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
def canonical_body_at_indent(content_indent):
    return "".join(
        line if line == "\n" else f"{' ' * content_indent}{line}"
        for line in canonical_installer_run.splitlines(keepends=True)
    )


canonical_run_body = canonical_body_at_indent(run_indent + 2)
if "".join(lines[run_start + 1:run_end]).encode("utf-8") != canonical_run_body.encode("utf-8"):
    fail("installer literal run block differs from the admitted canonical block")

# The admitted raw body must not be duplicated in another literal scalar.  This
# blocks skipped canonical-name decoys and anonymous canonical blocks alike.
any_run_key_pattern = re.compile(r"^(?P<indent> *)run:")
for index, line in enumerate(lines):
    match = any_run_key_pattern.match(without_line_ending(line))
    if not match or index == run_start:
        continue
    candidate_indent = len(match.group("indent"))
    candidate_end = literal_body_end(index, candidate_indent, len(lines))
    candidate_body = "".join(lines[index + 1:candidate_end])
    expected_body = canonical_body_at_indent(candidate_indent + 2)
    if candidate_body.encode("utf-8") == expected_body.encode("utf-8"):
        fail("canonical installer literal run block appears outside id: download")

mount_matches = exact_named_steps("Mount DMG and Install")
if len(mount_matches) != 1:
    fail("expected one exact Mount DMG and Install step")
mount_start, mount_indent = mount_matches[0]
if mount_start <= step_start:
    fail("mount/install flow must occur after the download producer")
mount_end = step_end_after(mount_start, mount_indent)
mount_body = "".join(lines[mount_start + 1:mount_end])
for required_line, description in [
    (f"{' ' * (mount_indent + 4)}DMG_PATH=\"${{{{ steps.download.outputs.dmg_path }}}}\"\n", "download output input"),
    (f"{' ' * (mount_indent + 4)}ditto \"$MOUNTPOINT/Omi.app\" \"/Applications/Omi.app\"\n", "mounted-app copy"),
]:
    if required_line not in mount_body:
        fail(f"mount/install flow missing exact {description}")
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
import subprocess
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


def add_skipped_canonical_decoy(quoted):
    active_starts = [index for index, line in enumerate(lines) if line == '      - name: Download DMG from GitHub Release\n']
    if len(active_starts) != 1:
        raise SystemExit(f"expected one active installer step, found {len(active_starts)}")
    active_start = active_starts[0]
    active_end = next(
        index for index in range(active_start + 1, len(lines)) if lines[index].startswith('      - ')
    )
    run_start = next(index for index in range(active_start + 1, active_end) if lines[index] == '        run: |\n')
    canonical_body = lines[run_start + 1:active_end]
    decoy_name = "'Download DMG from GitHub Release'" if quoted else "Download DMG from GitHub Release"
    decoy = [
        f'      - name: {decoy_name}\n',
        '        if: ${{ false }}\n',
        '        run: |\n',
        *canonical_body,
    ]
    lines[active_start:active_start] = decoy
    active_start += len(decoy)
    lines[active_start] = '      - name: Fetch installer asset\n'
    active_end += len(decoy)
    active_patterns = [
        index
        for index in range(active_start + 1, active_end)
        if '--pattern "omi.dmg"' in lines[index]
    ]
    if len(active_patterns) != 1:
        raise SystemExit("active canonical pattern line not found")
    lines[active_patterns[0]] = lines[active_patterns[0]].replace('"omi.dmg"', '"*.dmg"')


def prove_decoy_topology_with_ruby(destination, mutation):
    ruby = r'''
require "yaml"
workflow = YAML.safe_load(File.read(ARGV.fetch(0)), aliases: false)
steps = workflow.fetch("jobs").fetch("test-install").fetch("steps")
producers = steps.select { |step| step["id"] == "download" }
abort "expected one active download producer" unless producers.length == 1
producer = producers.fetch(0)
abort "wildcard producer was not renamed" unless producer["name"] == "Fetch installer asset"
abort "wildcard pattern is not owned by id: download" unless producer.fetch("run").include?('--pattern "*.dmg"')
mounts = steps.select { |step| step["name"] == "Mount DMG and Install" }
abort "expected one mount/install flow" unless mounts.length == 1
mount = mounts.fetch(0).fetch("run")
abort "mount does not consume id: download output" unless mount.include?("steps.download.outputs.dmg_path")
abort "mount flow does not install the mounted app" unless mount.include?("ditto \"$MOUNTPOINT/Omi.app\" \"/Applications/Omi.app\"")
'''
    subprocess.run(["ruby", "-e", ruby, str(destination)], check=True)
    print(f"Ruby YAML topology proof passed: {mutation}")


if mutation == "canonical":
    pass
elif mutation == "unrelated-yaml":
    matches = [index for index, line in enumerate(lines) if "timeout-minutes: 15" in line]
    if len(matches) != 1:
        raise SystemExit(f"expected one unrelated timeout line, found {len(matches)}")
    lines[matches[0]] = lines[matches[0]].replace("timeout-minutes: 15", "timeout-minutes: 16")
elif mutation == "unquoted-canonical-decoy-active-wildcard":
    add_skipped_canonical_decoy(quoted=False)
elif mutation == "quoted-canonical-decoy-active-wildcard":
    add_skipped_canonical_decoy(quoted=True)
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
if mutation in {"unquoted-canonical-decoy-active-wildcard", "quoted-canonical-decoy-active-wildcard"}:
    prove_decoy_topology_with_ruby(destination, mutation)
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
run_mutation unquoted-canonical-decoy-active-wildcard unquoted-canonical-decoy-active-wildcard
run_mutation quoted-canonical-decoy-active-wildcard quoted-canonical-decoy-active-wildcard
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
