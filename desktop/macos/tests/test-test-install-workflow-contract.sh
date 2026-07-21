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


if re.search(r"(?m)(?:^|[ \t:\[\]{},])(?:&|\*)[A-Za-z_][A-Za-z0-9_-]*", workflow_text) or re.search(
    r"(?m)^ *<<:", workflow_text
):
    fail("workflow must not use YAML anchors, aliases, or merges")


def mapping_end_after(mapping_start, mapping_indent, limit=len(lines)):
    for index in range(mapping_start + 1, limit):
        bare_line = without_line_ending(lines[index])
        if bare_line.strip() and leading_spaces(bare_line) <= mapping_indent:
            return index
    return limit


top_level_key_pattern = re.compile(r"^(?P<key>[^ #][^:]*):")
top_level_keys = [
    (index, match.group("key"))
    for index, line in enumerate(lines)
    if (match := top_level_key_pattern.match(without_line_ending(line)))
]
if any(key not in {"name", "on", "jobs"} for _, key in top_level_keys):
    fail("workflow may not add top-level execution-affecting fields")
if any(key.strip("\"'") == "jobs" and key != "jobs" for _, key in top_level_keys):
    fail("jobs mapping must not use a quoted or alternate spelling")
top_level_jobs = [index for index, key in top_level_keys if key == "jobs"]
if len(top_level_jobs) != 1:
    fail("expected exactly one literal top-level jobs: mapping")
jobs_start = top_level_jobs[0]
jobs_end = mapping_end_after(jobs_start, 0)

job_key_pattern = re.compile(r"^  (?P<key>[^ #][^:]*):(?:\s*(?:#.*)?)$")
job_key_lines = [
    (index, match.group("key"))
    for index in range(jobs_start + 1, jobs_end)
    if (match := job_key_pattern.match(without_line_ending(lines[index])))
]
test_install_keys = [index for index, key in job_key_lines if key == "test-install"]
if len(test_install_keys) != 1:
    fail("expected exactly one exact unquoted test-install: job key")
if any(key.strip("\"'") == "test-install" and key != "test-install" for _, key in job_key_lines):
    fail("test-install job key must not use a quoted or alternate spelling")
job_start = test_install_keys[0]
job_end = next((index for index, _ in job_key_lines if index > job_start), jobs_end)


def direct_job_field_lines(name):
    pattern = re.compile(rf"^    {re.escape(name)}:(?P<value>.*)$")
    return [
        (index, match.group("value"))
        for index in range(job_start + 1, job_end)
        if (match := pattern.match(without_line_ending(lines[index])))
    ]


for name, expected in (("runs-on", " macos-15"), ("timeout-minutes", " 15"), ("steps", "")):
    fields = direct_job_field_lines(name)
    if len(fields) != 1 or fields[0][1] != expected:
        fail(f"test-install must retain the exact {name}: {expected.strip() or 'mapping'} contract")

allowed_job_fields = {"runs-on", "timeout-minutes", "steps"}
for index in range(job_start + 1, job_end):
    match = re.match(r"^    (?P<name>[^ #][^:]*):", without_line_ending(lines[index]))
    if match and match.group("name") not in allowed_job_fields:
        fail(f"test-install may not add execution-affecting job field: {match.group('name')}")

steps_start = direct_job_field_lines("steps")[0][0]
steps_end = mapping_end_after(steps_start, 4, job_end)
step_starts = [
    index
    for index in range(steps_start + 1, steps_end)
    if re.match(r"^      - ", without_line_ending(lines[index]))
]
if not step_starts:
    fail("test-install must contain one literal steps: sequence")


def step_end_after(step_start):
    return next((index for index in step_starts if index > step_start), steps_end)


def exact_step_start(name):
    exact = f"      - name: {name}"
    mentions = [
        index
        for index, line in enumerate(lines)
        if re.match(r"^ *-\s+name:", without_line_ending(line)) and name in without_line_ending(line)
    ]
    if any(without_line_ending(lines[index]) != exact for index in mentions):
        fail(f"{name} step name must use one exact unquoted canonical spelling")
    matches = [index for index in step_starts if without_line_ending(lines[index]) == exact]
    if len(matches) != 1 or mentions != matches:
        fail(f"expected exactly one executable {name!r} step in jobs.test-install.steps")
    return matches[0]


def literal_body_end(run_start, run_indent, limit):
    for index in range(run_start + 1, limit):
        bare_line = without_line_ending(lines[index])
        if bare_line.strip(" ") and leading_spaces(bare_line) <= run_indent:
            return index
    return limit


step_start = exact_step_start(target_name)
step_end = step_end_after(step_start)
run_start = step_start + 4
expected_download_header = [
    f"      - name: {target_name}",
    "        id: download",
    "        env:",
    "          GH_TOKEN: ${{ github.token }}",
    "        run: |",
]
if [without_line_ending(line) for line in lines[step_start:run_start + 1]] != expected_download_header:
    fail("canonical download step must contain only its exact name, id, env, and run fields")
run_indent = 8
run_end = literal_body_end(run_start, run_indent, step_end)
if run_end != step_end:
    fail("installer literal run block must occupy the rest of its executable step")

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
def body_at_indent(body, content_indent):
    return "".join(
        line if line == "\n" else f"{' ' * content_indent}{line}"
        for line in body.splitlines(keepends=True)
    )


canonical_run_body = body_at_indent(canonical_installer_run, run_indent + 2)
if "".join(lines[run_start + 1:run_end]).encode("utf-8") != canonical_run_body.encode("utf-8"):
    fail("installer literal run block differs from the admitted canonical block")

mount_name = "Mount DMG and Install"
mount_start = exact_step_start(mount_name)
if mount_start <= step_start:
    fail("mount/install flow must occur after the download producer")
mount_end = step_end_after(mount_start)
mount_field_indent = 8
if [without_line_ending(line) for line in lines[mount_start:mount_start + 2]] != [
    f"      - name: {mount_name}",
    "        run: |",
]:
    fail("mount/install step must consist of its exact name and run: | fields")
mount_run_start = mount_start + 1
mount_run_end = literal_body_end(mount_run_start, mount_field_indent, mount_end)
if mount_run_end != mount_end:
    fail("mount/install literal run block must occupy the rest of its executable step")

canonical_mount_run = '''set -euo pipefail
DMG_PATH="${{ steps.download.outputs.dmg_path }}"
MOUNTPOINT="$RUNNER_TEMP/omi-install-mount-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
DEVICE=""

cleanup() {
  local exit_code=$?
  if [[ -n "$DEVICE" ]]; then
    hdiutil detach "$DEVICE" -quiet || true
  fi
  rm -rf "$MOUNTPOINT" "$(dirname "$DMG_PATH")"
  exit "$exit_code"
}
trap cleanup EXIT

mkdir -p "$MOUNTPOINT"
xattr -d com.apple.quarantine "$DMG_PATH" 2>/dev/null || true
DEVICE=$(hdiutil attach "$DMG_PATH" -nobrowse -readonly -mountpoint "$MOUNTPOINT" | awk '/^\\/dev\\// { print $1; exit }')
[[ -n "$DEVICE" ]]
[[ -d "$MOUNTPOINT/Omi.app" ]]
echo "Mounted $DMG_PATH at $MOUNTPOINT ($DEVICE)"

# Use ditto to preserve extended attributes from the exact mounted image.
ditto "$MOUNTPOINT/Omi.app" "/Applications/Omi.app"

echo "App installed to /Applications"

'''
canonical_mount_body = body_at_indent(canonical_mount_run, mount_field_indent + 2)
if "".join(lines[mount_run_start + 1:mount_run_end]).encode("utf-8") != canonical_mount_body.encode("utf-8"):
    fail("mount/install literal run block differs from the admitted canonical block")

# Canonical scripts have a single raw owner.  A byte-identical body in any
# other literal scalar is a decoy, not an alternate execution path.
literal_scalar_pattern = re.compile(r"^(?P<indent> *)[^#][^:]*:\s*\|[+-]?$")
for canonical_body, owner, label in (
    (canonical_installer_run, run_start, "installer"),
    (canonical_mount_run, mount_run_start, "mount/install"),
):
    owners = []
    for index, line in enumerate(lines):
        match = literal_scalar_pattern.match(without_line_ending(line))
        if not match:
            continue
        candidate_indent = len(match.group("indent"))
        candidate_end = literal_body_end(index, candidate_indent, len(lines))
        if "".join(lines[index + 1:candidate_end]).encode("utf-8") == body_at_indent(
            canonical_body, candidate_indent + 2
        ).encode("utf-8"):
            owners.append(index)
    if owners != [owner]:
        fail(f"canonical {label} literal run block must belong only to jobs.test-install.steps")
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


def mount_step_bounds():
    starts = [index for index, line in enumerate(lines) if line == '      - name: Mount DMG and Install\n']
    if len(starts) != 1:
        raise SystemExit(f"expected one canonical mount step, found {len(starts)}")
    start = starts[0]
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith('      - ')),
        len(lines),
    )
    run_start = next(index for index in range(start + 1, end) if lines[index] == '        run: |\n')
    return start, run_start, end


def mount_line_index(text):
    _, run_start, end = mount_step_bounds()
    matches = [index for index in range(run_start + 1, end) if lines[index] == text]
    if len(matches) != 1:
        raise SystemExit(f"expected one canonical mount line {text!r}, found {len(matches)}")
    return matches[0]


def mount_run_body():
    _, run_start, end = mount_step_bounds()
    return lines[run_start + 1:end]


def test_install_job_start():
    starts = [index for index, line in enumerate(lines) if line == '  test-install:\n']
    if len(starts) != 1:
        raise SystemExit(f"expected one literal test-install job, found {len(starts)}")
    return starts[0]


def alternate_test_install_job(key):
    return [
        f"  {key}:\n",
        "    runs-on: macos-15\n",
        "    timeout-minutes: 15\n",
        "    steps:\n",
        "      - name: Download alternate installer\n",
        "        run: |\n",
        "          echo alternate installer\n",
        "      - name: Install alternate installer\n",
        "        run: |\n",
        "          echo alternate install\n",
    ]


def add_canonical_job_decoy(position, quoted):
    start = test_install_job_start()
    lines[start] = "  canonical-contract-decoy:\n"
    alternate = alternate_test_install_job('"test-install"' if quoted else "test-install")
    if position == "before":
        lines[start:start] = alternate
    elif position == "after":
        lines.extend(alternate)
    else:
        raise SystemExit(f"unknown canonical job decoy position: {position}")


def prove_canonical_job_decoy_topology_with_ruby(destination, mutation):
    ruby = r'''
require "yaml"
workflow = YAML.safe_load(File.read(ARGV.fetch(0)), aliases: false)
jobs = workflow.fetch("jobs")
actual = jobs.fetch("test-install")
decoy = jobs.fetch("canonical-contract-decoy")
abort "real test-install is not alternate" if actual.fetch("steps").any? { |step| step["name"] == "Download DMG from GitHub Release" }
abort "canonical download is missing from decoy" unless decoy.fetch("steps").any? { |step| step["name"] == "Download DMG from GitHub Release" }
abort "canonical mount is missing from decoy" unless decoy.fetch("steps").any? { |step| step["name"] == "Mount DMG and Install" }
'''
    subprocess.run(["ruby", "-e", ruby, str(destination)], check=True)
    print(f"Ruby YAML executable-topology proof passed: {mutation}")


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
    matches = [index for index, line in enumerate(lines) if line == "name: Test macOS Installation\n"]
    if len(matches) != 1:
        raise SystemExit(f"expected one workflow display-name line, found {len(matches)}")
    lines[matches[0]] = "name: Test macOS Installation contract mutation\n"
elif mutation in {
    "canonical-job-decoy-before-unquoted",
    "canonical-job-decoy-after-unquoted",
    "canonical-job-decoy-before-quoted",
    "canonical-job-decoy-after-quoted",
}:
    add_canonical_job_decoy(
        "before" if "-before-" in mutation else "after",
        quoted=mutation.endswith("-quoted"),
    )
elif mutation == "workflow-defaults-shell-override":
    index = next(index for index, line in enumerate(lines) if line == "on:\n")
    lines[index:index] = [
        "defaults:\n",
        "  run:\n",
        "    shell: bash -c 'exit 0' {0}\n",
        "\n",
    ]
elif mutation == "test-install-defaults-shell-override":
    index = test_install_job_start() + 1
    lines[index:index] = [
        "    defaults:\n",
        "      run:\n",
        "        shell: bash -c 'exit 0' {0}\n",
    ]
elif mutation == "download-step-shell-override":
    index = lines.index("        id: download\n") + 1
    lines[index:index] = ["        shell: bash -c 'exit 0' {0}\n"]
elif mutation == "test-install-if-false":
    index = test_install_job_start() + 1
    lines[index:index] = ["    if: github.event_name == 'never'\n"]
elif mutation == "download-step-if-false":
    index = lines.index("        id: download\n") + 1
    lines[index:index] = ["        if: github.event_name == 'never'\n"]
elif mutation == "test-install-env-bash-env":
    index = test_install_job_start() + 1
    lines[index:index] = ["    env:\n", "      BASH_ENV: /tmp/skip-canonical-steps\n"]
elif mutation == "download-step-env-path":
    index = lines.index("          GH_TOKEN: ${{ github.token }}\n") + 1
    lines[index:index] = ["          PATH: /tmp/alternate-bin\n"]
elif mutation == "test-install-continue-on-error":
    index = test_install_job_start() + 1
    lines[index:index] = ["    continue-on-error: true\n"]
elif mutation == "unrelated-job-defaults-shell":
    lines.extend([
        "  unrelated-defaults:\n",
        "    runs-on: macos-15\n",
        "    defaults:\n",
        "      run:\n",
        "        shell: bash -c 'exit 0' {0}\n",
        "    steps:\n",
        "      - run: echo unrelated\n",
    ])
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
elif mutation == "mount-dead-branch-dmg-assignment-alternate":
    index = mount_line_index('          DMG_PATH="${{ steps.download.outputs.dmg_path }}"\n')
    lines[index:index + 1] = [
        '          if false; then\n',
        '            DMG_PATH="${{ steps.download.outputs.dmg_path }}"\n',
        '          fi\n',
        '          DMG_PATH="$RUNNER_TEMP/attacker.dmg"\n',
    ]
elif mutation == "mount-dead-branch-ditto-alternate-source":
    index = mount_line_index('          ditto "$MOUNTPOINT/Omi.app" "/Applications/Omi.app"\n')
    lines[index:index + 1] = [
        '          if false; then\n',
        '            ditto "$MOUNTPOINT/Omi.app" "/Applications/Omi.app"\n',
        '          fi\n',
        '          ditto "/tmp/attacker/Omi.app" "/Applications/Omi.app"\n',
    ]
elif mutation == "mount-exit-before-dmg-assignment":
    index = mount_line_index('          DMG_PATH="${{ steps.download.outputs.dmg_path }}"\n')
    lines[index:index] = ['          exit 0\n']
elif mutation == "mount-exit-before-ditto":
    index = mount_line_index('          ditto "$MOUNTPOINT/Omi.app" "/Applications/Omi.app"\n')
    lines[index:index] = ['          exit 0\n']
elif mutation == "mount-assignment-override":
    index = mount_line_index('          DMG_PATH="${{ steps.download.outputs.dmg_path }}"\n')
    lines[index + 1:index + 1] = ['          DMG_PATH="$RUNNER_TEMP/attacker.dmg"\n']
elif mutation == "mount-alternate-copy-after-ditto":
    index = mount_line_index('          ditto "$MOUNTPOINT/Omi.app" "/Applications/Omi.app"\n')
    lines[index + 1:index + 1] = ['          ditto "/tmp/attacker/Omi.app" "/Applications/Omi.app"\n']
elif mutation == "mount-comment":
    index = mount_line_index('          set -euo pipefail\n')
    lines[index + 1:index + 1] = ['          # Attacker-controlled no-op in the protected block.\n']
elif mutation == "mount-command-substitution":
    index = mount_line_index('          set -euo pipefail\n')
    lines[index + 1:index + 1] = ['          : "$(printf attacker)"\n']
elif mutation == "mount-backtick":
    index = mount_line_index('          set -euo pipefail\n')
    lines[index + 1:index + 1] = ['          : `printf attacker`\n']
elif mutation == "mount-wrapper":
    index = mount_line_index('          ditto "$MOUNTPOINT/Omi.app" "/Applications/Omi.app"\n')
    lines[index] = '          command ditto "$MOUNTPOINT/Omi.app" "/Applications/Omi.app"\n'
elif mutation == "mount-control-flow":
    index = mount_line_index('          set -euo pipefail\n')
    _, _, end = mount_step_bounds()
    lines[index:index] = ['          if true; then\n']
    lines[end + 1:end + 1] = ['          fi\n']
elif mutation == "mount-duplicate-step":
    start, _, end = mount_step_bounds()
    lines[end:end] = lines[start:end]
elif mutation == "mount-quoted-step":
    start, _, _ = mount_step_bounds()
    lines[start] = "      - name: 'Mount DMG and Install'\n"
elif mutation == "mount-renamed-step":
    start, _, _ = mount_step_bounds()
    lines[start] = '      - name: Install mounted DMG\n'
elif mutation == "mount-extra-canonical-block-decoy":
    _, _, end = mount_step_bounds()
    lines[end:end] = [
        '      - name: Installer mount decoy\n',
        '        run: |\n',
        *mount_run_body(),
    ]
else:
    raise SystemExit(f"unknown mutation: {mutation}")

destination.write_text(''.join(lines))
if mutation in {"unquoted-canonical-decoy-active-wildcard", "quoted-canonical-decoy-active-wildcard"}:
    prove_decoy_topology_with_ruby(destination, mutation)
if mutation.startswith("canonical-job-decoy-"):
    prove_canonical_job_decoy_topology_with_ruby(destination, mutation)
PY

  ruby -e 'require "yaml"; YAML.safe_load(File.read(ARGV.fetch(0)), aliases: false)' "$mutated_workflow"
  if [[ "$mutation" != "unquoted-canonical-decoy-active-wildcard" && "$mutation" != "quoted-canonical-decoy-active-wildcard" ]]; then
    actionlint -shellcheck= "$mutated_workflow"
  fi

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
run_mutation canonical-job-decoy-before-unquoted canonical-job-decoy-before-unquoted
run_mutation canonical-job-decoy-after-unquoted canonical-job-decoy-after-unquoted
run_mutation canonical-job-decoy-before-quoted canonical-job-decoy-before-quoted
run_mutation canonical-job-decoy-after-quoted canonical-job-decoy-after-quoted
run_mutation workflow-defaults-shell-override workflow-defaults-shell-override
run_mutation test-install-defaults-shell-override test-install-defaults-shell-override
run_mutation download-step-shell-override download-step-shell-override
run_mutation test-install-if-false test-install-if-false
run_mutation download-step-if-false download-step-if-false
run_mutation test-install-env-bash-env test-install-env-bash-env
run_mutation download-step-env-path download-step-env-path
run_mutation test-install-continue-on-error test-install-continue-on-error
run_mutation unrelated-job-defaults-shell unrelated-job-defaults-shell accept
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
run_mutation mount-dead-branch-dmg-assignment-alternate mount-dead-branch-dmg-assignment-alternate
run_mutation mount-dead-branch-ditto-alternate-source mount-dead-branch-ditto-alternate-source
run_mutation mount-exit-before-dmg-assignment mount-exit-before-dmg-assignment
run_mutation mount-exit-before-ditto mount-exit-before-ditto
run_mutation mount-assignment-override mount-assignment-override
run_mutation mount-alternate-copy-after-ditto mount-alternate-copy-after-ditto
run_mutation mount-comment mount-comment
run_mutation mount-command-substitution mount-command-substitution
run_mutation mount-backtick mount-backtick
run_mutation mount-wrapper mount-wrapper
run_mutation mount-control-flow mount-control-flow
run_mutation mount-duplicate-step mount-duplicate-step
run_mutation mount-quoted-step mount-quoted-step
run_mutation mount-renamed-step mount-renamed-step
run_mutation mount-extra-canonical-block-decoy mount-extra-canonical-block-decoy

echo "test-install workflow exact-DMG contract passed"
