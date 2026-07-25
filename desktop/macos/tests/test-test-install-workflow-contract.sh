#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_WORKFLOW="$SCRIPT_DIR/../.github/workflows/test-install.yml"
WORKFLOW="${2:-$DEFAULT_WORKFLOW}"

# Self-provision actionlint via Go when not on PATH. The GitHub-hosted macOS
# runner includes Go but not actionlint; repo-checks.yml installs it separately
# for its own workflow-lint step, but the desktop launcher-script-tests loop
# does not.
if ! command -v actionlint >/dev/null 2>&1; then
  if command -v go >/dev/null 2>&1; then
    export GOBIN="${GOBIN:-$(mktemp -d)}"
    export PATH="$GOBIN:$PATH"
    go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12 >&2
  else
    echo "actionlint is required but not installed and Go is not available to build it" >&2
    exit 1
  fi
fi

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

strict_check_workflow() {
  ruby - "$WORKFLOW" "$SCRIPT_DIR/fixtures/test-install-job-contract.yml" "$SCRIPT_DIR/fixtures/test-install-workflow-prefix-contract.yml" <<'RUBY'
require "yaml"


def fail(message)
  abort("FAIL: #{message}")
end


workflow_path, job_contract_path, prefix_contract_path = ARGV
workflow_bytes = File.binread(workflow_path)
prefix_bytes = File.binread(prefix_contract_path)
fail("workflow prefix contract must end with literal jobs:\\n") unless prefix_bytes.end_with?("jobs:\n".b)
fail("workflow must begin with the canonical top-level prefix exactly once") unless workflow_bytes.start_with?(prefix_bytes) && workflow_bytes.scan(prefix_bytes).length == 1

workflow_text = File.read(workflow_path, encoding: "UTF-8")
job_contract_text = File.read(job_contract_path, encoding: "UTF-8")

begin
  stream = Psych.parse_stream(workflow_text)
  fail("workflow must contain exactly one YAML document") unless stream.children.length == 1
  root = stream.children.fetch(0).root
  fail("workflow YAML root must be a mapping") unless root.is_a?(Psych::Nodes::Mapping)
  root_pairs = root.children.each_slice(2).to_a
  fail("workflow YAML root has an incomplete mapping pair") unless root_pairs.all? { |pair| pair.length == 2 }
  fail("workflow top-level mapping must contain only the canonical prefix keys") unless root_pairs.length == 3
  root_key_nodes = root_pairs.map(&:first)
  fail("workflow top-level keys must be plain, untagged scalars") unless root_key_nodes.all? do |key|
    key.is_a?(Psych::Nodes::Scalar) && key.plain && !key.quoted && key.tag.nil? && key.anchor.nil?
  end
  fail("workflow top-level keys must match the canonical prefix") unless root_key_nodes.map(&:value) == ["name", "on", "jobs"]
  jobs_pairs = root_pairs.select do |key, _value|
    key.is_a?(Psych::Nodes::Scalar) && key.plain && !key.quoted && key.tag.nil? && key.anchor.nil? && key.value == "jobs"
  end
  fail("workflow must contain exactly one plain top-level jobs mapping") unless jobs_pairs.length == 1
  jobs_node = jobs_pairs.fetch(0).fetch(1)
  fail("workflow jobs must be a mapping") unless jobs_node.is_a?(Psych::Nodes::Mapping)

  job_pairs = jobs_node.children.each_slice(2).to_a
  fail("workflow jobs has an incomplete mapping pair") unless job_pairs.all? { |pair| pair.length == 2 }
  job_key_nodes = job_pairs.map(&:first)
  fail("workflow job keys must be plain, untagged scalars") unless job_key_nodes.all? do |key|
    key.is_a?(Psych::Nodes::Scalar) && key.plain && !key.quoted && key.tag.nil? && key.anchor.nil? && key.value.is_a?(String)
  end
  ast_job_keys = job_key_nodes.map(&:value)
  fail("workflow job keys must be unique") unless ast_job_keys.uniq.length == ast_job_keys.length
  fail("workflow must contain exactly one literal test-install job key") unless ast_job_keys.count("test-install") == 1

  workflow = YAML.safe_load(workflow_text, aliases: false)
  job_contract = YAML.safe_load(job_contract_text, aliases: false)
rescue Psych::Exception, ArgumentError, EncodingError => error
  fail("workflow YAML must safely parse without aliases: #{error.message}")
end

fail("workflow YAML root must safely load as a mapping") unless workflow.is_a?(Hash)
fail("workflow jobs must safely load as a mapping") unless workflow["jobs"].is_a?(Hash)
fail("workflow loaded job keys must be strings") unless workflow["jobs"].keys.all? { |key| key.is_a?(String) }
fail("workflow loaded job keys must match the parsed job keys") unless workflow["jobs"].keys.sort == ast_job_keys.sort

fail("test-install job contract fixture must safely load as a mapping") unless job_contract.is_a?(Hash)
fail("test-install job contract fixture must contain exactly one job") unless job_contract.keys == ["test-install"]
expected_job = job_contract["test-install"]
actual_job = workflow["jobs"]["test-install"]
fail("test-install job contract fixture must define a mapping") unless expected_job.is_a?(Hash)
fail("workflow test-install job must safely load as a mapping") unless actual_job.is_a?(Hash)
fail("workflow test-install job must semantically match the complete-job fixture") unless actual_job == expected_job
RUBY

  python3 - "$WORKFLOW" "$SCRIPT_DIR/fixtures/test-install-job-contract.yml" <<'PY'
from pathlib import Path
import re
import sys


def fail(message):
    raise SystemExit(f"FAIL: {message}")


workflow_path = Path(sys.argv[1])
contract_path = Path(sys.argv[2])
workflow_bytes = workflow_path.read_bytes()
contract_bytes = contract_path.read_bytes()
try:
    workflow_text = workflow_bytes.decode("utf-8")
except UnicodeDecodeError as error:
    fail(f"workflow must be UTF-8: {error}")

if not contract_bytes.endswith(b"\n"):
    fail("test-install byte contract must end with one literal LF")
if re.search(r"(?m)(?:^|[ \t:\[\]{},])(?:&|\*)[A-Za-z_][A-Za-z0-9_-]*", workflow_text) or re.search(
    r"(?m)^ *<<:", workflow_text
):
    fail("workflow must not use YAML anchors, aliases, or merges")

lines = workflow_text.splitlines(keepends=True)


def without_line_ending(line):
    return line.rstrip("\r\n")


def leading_spaces(line):
    return len(line) - len(line.lstrip(" "))


def mapping_end_after(mapping_start, mapping_indent, limit):
    for index in range(mapping_start + 1, limit):
        line = without_line_ending(lines[index])
        if line.strip() and leading_spaces(line) <= mapping_indent:
            return index
    return limit


jobs_starts = [index for index, line in enumerate(lines) if line == "jobs:\n"]
if len(jobs_starts) != 1 or lines[jobs_starts[0]] != "jobs:\n":
    fail("expected exactly one literal top-level jobs: mapping")
jobs_start = jobs_starts[0]
jobs_end = mapping_end_after(jobs_start, 0, len(lines))

job_key = re.compile(r"^  (?P<key>[^ #][^:]*):(?:\s*(?:#.*)?)$")
job_keys = [
    (index, match.group("key"))
    for index in range(jobs_start + 1, jobs_end)
    if (match := job_key.match(without_line_ending(lines[index])))
]
test_install_starts = [index for index, key in job_keys if key == "test-install"]
if len(test_install_starts) != 1 or lines[test_install_starts[0]] != "  test-install:\n":
    fail("expected exactly one exact unquoted jobs.test-install job key")
job_start = test_install_starts[0]
job_end = next((index for index, _ in job_keys if index > job_start), jobs_end)
actual_block = "".join(lines[job_start:job_end]).encode("utf-8")

if workflow_bytes.count(contract_bytes) != 1:
    fail("admitted canonical test-install block must occur exactly once")
if actual_block != contract_bytes:
    fail("jobs.test-install must byte-match the admitted canonical block")
PY
}

strict_check_workflow

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
elif mutation == "unrelated-top-level-metadata":
    index = next(index for index, line in enumerate(lines) if line == "name: Test macOS Installation\n") + 1
    lines[index:index] = ["run-name: installer-contract ${{ github.event_name }}\n"]
elif mutation == "workflow-permissions-none":
    index = next(index for index, line in enumerate(lines) if line == "name: Test macOS Installation\n") + 1
    lines[index:index] = ["permissions: {}\n"]
elif mutation == "workflow-permissions-contents-none":
    index = next(index for index, line in enumerate(lines) if line == "name: Test macOS Installation\n") + 1
    lines[index:index] = ["permissions: {contents: none}\n"]
elif mutation == "workflow-concurrency-cancel":
    index = next(index for index, line in enumerate(lines) if line == "name: Test macOS Installation\n") + 1
    lines[index:index] = [
        "concurrency:\n",
        "  group: installer-contract\n",
        "  cancel-in-progress: true\n",
    ]
elif mutation == "workflow-permissions-after-jobs":
    lines.extend(["permissions: {contents: none}\n"])
elif mutation == "pre-download-github-env-bash-env":
    index = next(index for index, line in enumerate(lines) if line == "      - name: Download DMG from GitHub Release\n")
    lines[index:index] = [
        "      - name: Poison BASH_ENV before canonical download\n",
        "        run: echo \"BASH_ENV=/tmp/discard-canonical\" >> \"$GITHUB_ENV\"\n",
        "\n",
    ]
elif mutation == "pre-download-github-path":
    index = next(index for index, line in enumerate(lines) if line == "      - name: Download DMG from GitHub Release\n")
    lines[index:index] = [
        "      - name: Poison PATH before canonical download\n",
        "        run: echo \"/tmp/attacker-bin\" >> \"$GITHUB_PATH\"\n",
        "\n",
    ]
elif mutation == "interposed-replacement":
    index = next(index for index, line in enumerate(lines) if line == "      - name: Mount DMG and Install\n")
    lines[index:index] = [
        "      - name: Replace downloaded disk image\n",
        "        run: echo attacker > \"$RUNNER_TEMP/omi-install-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}/omi.dmg\"\n",
        "\n",
    ]
elif mutation == "post-download-output-overwrite":
    index = next(index for index, line in enumerate(lines) if line == "      - name: Mount DMG and Install\n")
    lines[index:index] = [
        "      - name: Overwrite post-download output\n",
        "        id: download-output-overwrite\n",
        "        run: echo \"dmg_path=$RUNNER_TEMP/attacker.dmg\" >> \"$GITHUB_OUTPUT\"\n",
        "\n",
    ]
elif mutation == "extra-action-step":
    index = next(index for index, line in enumerate(lines) if line == "      - name: Download DMG from GitHub Release\n")
    lines[index:index] = [
        "      - name: Add action before installer download\n",
        "        uses: actions/checkout@v4\n",
        "\n",
    ]
elif mutation == "reorder":
    system_start = next(index for index, line in enumerate(lines) if line == "      - name: System Info\n")
    download_start = next(index for index, line in enumerate(lines) if line == "      - name: Download DMG from GitHub Release\n")
    system_step = lines[system_start:download_start]
    del lines[system_start:download_start]
    mount_start = next(index for index, line in enumerate(lines) if line == "      - name: Mount DMG and Install\n")
    lines[mount_start:mount_start] = system_step
elif mutation == "modified-checkout-action-input":
    index = next(index for index, line in enumerate(lines) if line == "      - name: Download DMG from GitHub Release\n")
    lines[index:index] = [
        "      - name: Checkout with substituted action input\n",
        "        uses: actions/checkout@v4\n",
        "        with:\n",
        "          ref: attacker-controlled-ref\n",
        "\n",
    ]
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
elif mutation in {"workflow-quoted-defaults-shell-override", "workflow-escaped-defaults-shell-override"}:
    index = next(index for index, line in enumerate(lines) if line == "on:\n")
    key = '"defaults"' if mutation == "workflow-quoted-defaults-shell-override" else '"def\\u0061ults"'
    lines[index:index] = [
        f"{key}:\n",
        "  run:\n",
        "    shell: bash -c 'exit 0' {0}\n",
        "\n",
    ]
elif mutation in {
    "workflow-quoted-env-bash-env",
    "workflow-escaped-env-bash-env",
    "workflow-explicit-env-bash-env",
    "workflow-tagged-env-bash-env",
}:
    index = next(index for index, line in enumerate(lines) if line == "on:\n")
    if mutation == "workflow-quoted-env-bash-env":
        addition = ['"env":\n', "  BASH_ENV: /tmp/skip-canonical-steps\n", "\n"]
    elif mutation == "workflow-escaped-env-bash-env":
        addition = ['"en\\u0076":\n', "  BASH_ENV: /tmp/skip-canonical-steps\n", "\n"]
    elif mutation == "workflow-explicit-env-bash-env":
        addition = ["? env\n", ": {BASH_ENV: /tmp/skip-canonical-steps}\n", "\n"]
    else:
        addition = ["!!str env:\n", "  BASH_ENV: /tmp/skip-canonical-steps\n", "\n"]
    lines[index:index] = addition
elif mutation == "semantic-duplicate-jobs":
    index = next(index for index, line in enumerate(lines) if line == "jobs:\n")
    lines[index:index] = ["? jobs\n", ": {}\n", "\n"]
elif mutation == "non-mapping-jobs":
    index = next(index for index, line in enumerate(lines) if line == "jobs:\n")
    lines[index:index + 1] = ["jobs: []\n", "\n", "unrelated-jobs:\n"]
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
elif mutation == "quoted-unrelated-job-key":
    lines.extend(alternate_test_install_job('"unrelated-quoted"'))
elif mutation == "binary-test-install-key":
    lines.extend(alternate_test_install_job("!!binary dGVzdC1pbnN0YWxs"))
elif mutation == "long-tagged-binary-test-install-key":
    lines.extend(alternate_test_install_job("!<tag:yaml.org,2002:binary> dGVzdC1pbnN0YWxs"))
elif mutation in {"workflow-bom", "workflow-crlf"}:
    pass
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
if mutation == "workflow-bom":
    destination.write_bytes(b"\xef\xbb\xbf" + destination.read_bytes())
elif mutation == "workflow-crlf":
    destination.write_bytes(destination.read_bytes().replace(b"\n", b"\r\n"))
if mutation in {"unquoted-canonical-decoy-active-wildcard", "quoted-canonical-decoy-active-wildcard"}:
    prove_decoy_topology_with_ruby(destination, mutation)
if mutation.startswith("canonical-job-decoy-"):
    prove_canonical_job_decoy_topology_with_ruby(destination, mutation)
PY

  ruby -e 'require "yaml"; YAML.safe_load(File.read(ARGV.fetch(0)), aliases: false)' "$mutated_workflow"
  if [[ "$mutation" != "unquoted-canonical-decoy-active-wildcard" && "$mutation" != "quoted-canonical-decoy-active-wildcard" && "$mutation" != "semantic-duplicate-jobs" && "$mutation" != "non-mapping-jobs" ]]; then
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
run_mutation unrelated-yaml unrelated-yaml
run_mutation unrelated-top-level-metadata unrelated-top-level-metadata
run_mutation workflow-permissions-none workflow-permissions-none
run_mutation workflow-permissions-contents-none workflow-permissions-contents-none
run_mutation workflow-concurrency-cancel workflow-concurrency-cancel
run_mutation workflow-permissions-after-jobs workflow-permissions-after-jobs
run_mutation workflow-bom workflow-bom
run_mutation workflow-crlf workflow-crlf
run_mutation pre-download-github-env-bash-env pre-download-github-env-bash-env
run_mutation pre-download-github-path pre-download-github-path
run_mutation interposed-replacement interposed-replacement
run_mutation post-download-output-overwrite post-download-output-overwrite
run_mutation extra-action-step extra-action-step
run_mutation reorder reorder
run_mutation modified-checkout-action-input modified-checkout-action-input
run_mutation canonical-job-decoy-before-unquoted canonical-job-decoy-before-unquoted
run_mutation canonical-job-decoy-after-unquoted canonical-job-decoy-after-unquoted
run_mutation canonical-job-decoy-before-quoted canonical-job-decoy-before-quoted
run_mutation canonical-job-decoy-after-quoted canonical-job-decoy-after-quoted
run_mutation workflow-defaults-shell-override workflow-defaults-shell-override
run_mutation workflow-quoted-defaults-shell-override workflow-quoted-defaults-shell-override
run_mutation workflow-escaped-defaults-shell-override workflow-escaped-defaults-shell-override
run_mutation workflow-quoted-env-bash-env workflow-quoted-env-bash-env
run_mutation workflow-escaped-env-bash-env workflow-escaped-env-bash-env
run_mutation workflow-explicit-env-bash-env workflow-explicit-env-bash-env
run_mutation workflow-tagged-env-bash-env workflow-tagged-env-bash-env
run_mutation semantic-duplicate-jobs semantic-duplicate-jobs
run_mutation non-mapping-jobs non-mapping-jobs
run_mutation test-install-defaults-shell-override test-install-defaults-shell-override
run_mutation download-step-shell-override download-step-shell-override
run_mutation test-install-if-false test-install-if-false
run_mutation download-step-if-false download-step-if-false
run_mutation test-install-env-bash-env test-install-env-bash-env
run_mutation download-step-env-path download-step-env-path
run_mutation test-install-continue-on-error test-install-continue-on-error
run_mutation unrelated-job-defaults-shell unrelated-job-defaults-shell accept
run_mutation quoted-unrelated-job-key quoted-unrelated-job-key
run_mutation binary-test-install-key binary-test-install-key
run_mutation long-tagged-binary-test-install-key long-tagged-binary-test-install-key
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
