#!/usr/bin/env python3
"""Hermetic lifecycle coverage for the trusted-M1 pre-tag readiness gate."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_READINESS = REPO_ROOT / "desktop/macos/scripts/pre-tag-readiness.sh"
INHERITED_GIT_CONTEXT = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_QUARANTINE_PATH",
    "GIT_WORK_TREE",
)


class PreTagReadinessBehaviorTests(unittest.TestCase):
    def run_git(self, cwd: Path, *args: str) -> str:
        completed = self.run_process(["git", *args], cwd=cwd)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def run_process(self, args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        process_env = dict(os.environ if env is None else env)
        for key in INHERITED_GIT_CONTEXT:
            process_env.pop(key, None)
        for key in tuple(process_env):
            if key.startswith("GIT_CONFIG_"):
                process_env.pop(key)
        process_env.update({
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
        })
        return subprocess.run(args, cwd=cwd, env=process_env, text=True, capture_output=True, check=False)

    def write_executable(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)

    def fixture(self, root: Path) -> tuple[Path, str, Path, Path]:
        origin = root / "origin.git"
        source = root / "source"
        self.assertEqual(self.run_process(["git", "init", "--bare", "--quiet", str(origin)], cwd=root).returncode, 0)
        self.assertEqual(self.run_process(["git", "clone", "--quiet", str(origin), str(source)], cwd=root).returncode, 0)
        scripts = source / "desktop/macos/scripts"
        scripts.mkdir(parents=True)
        (source / "backend").mkdir()
        os.symlink(REAL_READINESS, scripts / "pre-tag-readiness.sh")
        self.write_executable(
            scripts / "qualification-swift-cache.sh",
            """#!/usr/bin/env bash
set -euo pipefail
log=${FAKE_READINESS_LOG:?}
receipt=${FAKE_READINESS_RECEIPT:?}
case "$1" in
  prepare)
    [[ $# -eq 5 ]]
    printf 'cache-prepare %s %s %s %s\\n' "$2" "$3" "$4" "$5" >> "$log"
    printf '{"source":%s,"token":"cache-token"}\\n' "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$3")"
    ;;
  release)
    [[ $# -eq 5 ]]
    [[ ! -e "$receipt" ]] || { echo 'receipt existed before cache release' >&2; exit 91; }
    printf 'cache-release %s %s %s %s\\n' "$2" "$3" "$4" "$5" >> "$log"
    [[ ${FAKE_FAIL_RELEASE:-} != cache ]] || exit 42
    ;;
  *) exit 2 ;;
esac
""",
        )
        self.write_executable(
            scripts / "qualification-lease-command.sh",
            """#!/usr/bin/env bash
set -euo pipefail
log=${FAKE_READINESS_LOG:?}
receipt=${FAKE_READINESS_RECEIPT:?}
case "$1" in
  acquire)
    [[ $# -eq 6 ]]
    printf 'lease-acquire %s %s %s %s %s\\n' "$2" "$3" "$4" "$5" "$6" >> "$log"
    printf '{"token":"lease-token"}\\n'
    ;;
  release)
    [[ $# -eq 6 ]]
    [[ ! -e "$receipt" ]] || { echo 'receipt existed before lease release' >&2; exit 92; }
    printf 'lease-release %s %s %s %s %s\\n' "$2" "$3" "$4" "$5" "$6" >> "$log"
    [[ ${FAKE_FAIL_RELEASE:-} != lease ]] || exit 43
    ;;
  *) exit 2 ;;
esac
""",
        )
        self.write_executable(
            scripts / "desktop-core-harness.sh",
            """#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == --readiness && $# -eq 1 ]]
[[ -n ${OMI_HARNESS_OWNERSHIP_TOKEN:-} && -n ${OMI_LOCAL_INSTANCE:-} && -n ${OMI_HARNESS_PORT_OFFSET:-} ]]
sha=$(git -C "$PWD" rev-parse HEAD)
root="$PWD/.harness/desktop-core/fake-readiness"
mkdir -p "$root"
printf '{"tier":"readiness","passed":true,"provider_mode":"offline","git_sha":"%s"}\\n' "$sha" > "$root/manifest.json"
printf 'harness %s %s %s\\n' "$sha" "$OMI_LOCAL_INSTANCE" "$OMI_HARNESS_OWNERSHIP_TOKEN" >> "${FAKE_READINESS_LOG:?}"
""",
        )
        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        self.write_executable(fake_bin / "uname", "#!/usr/bin/env bash\nprintf 'Darwin\\n'\n")
        self.run_git(source, "config", "user.email", "readiness-test@example.invalid")
        self.run_git(source, "config", "user.name", "Readiness Test")
        self.run_git(source, "add", ".")
        self.run_git(source, "commit", "--quiet", "-m", "readiness fixture")
        self.run_git(source, "branch", "-M", "main")
        self.run_git(source, "push", "--quiet", "-u", "origin", "main")
        return source, self.run_git(source, "rev-parse", "HEAD"), fake_bin, scripts / "pre-tag-readiness.sh"

    def run_readiness(self, root: Path, *, failed_release: str = "") -> tuple[subprocess.CompletedProcess[str], dict[str, object], list[str], str]:
        source, sha, fake_bin, readiness = self.fixture(root)
        receipt = root / "evidence/readiness.json"
        log = root / "operations.log"
        env = {
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_READINESS_LOG": str(log),
            "FAKE_READINESS_RECEIPT": str(receipt),
            "FAKE_FAIL_RELEASE": failed_release,
            "TMPDIR": str(root / "tmp"),
            "OMI_QUALIFICATION_LEASE_ROOT": str(root / "lease-root"),
        }
        (root / "tmp").mkdir()
        completed = self.run_process(
            [str(readiness), "--evidence", str(receipt), "--source-repository", str(source), sha], cwd=source, env=env
        )
        self.assertTrue(receipt.is_file(), completed.stderr)
        return completed, json.loads(receipt.read_text(encoding="utf-8")), log.read_text(encoding="utf-8").splitlines(), sha

    def test_success_receipt_follows_exact_sha_bound_authenticated_releases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed, receipt, operations, sha = self.run_readiness(Path(tmp))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["source_sha"], sha)
        self.assertEqual([line.split()[0] for line in operations], [
            "cache-prepare", "lease-acquire", "harness", "lease-release", "cache-release",
        ])
        cache_prepare = operations[0].split()
        lease_acquire = operations[1].split()
        harness = operations[2].split()
        lease_release = operations[3].split()
        cache_release = operations[4].split()
        cache_id, readiness_id = cache_prepare[3], lease_acquire[2]
        self.assertNotEqual(cache_id, readiness_id)
        self.assertTrue(cache_id.startswith(f"cache-readiness-{sha[:12]}-"))
        self.assertTrue(readiness_id.startswith(f"readiness-{sha[:12]}-"))
        self.assertEqual(cache_prepare[1:3], [sha, lease_acquire[1]])
        self.assertEqual(harness[1:], [sha, readiness_id, "lease-token"])
        self.assertEqual(lease_release[1:4], [lease_acquire[1], readiness_id, "lease-token"])
        self.assertEqual(cache_release[1:], [sha, cache_id, cache_prepare[4], "cache-token"])

    def test_cleanup_failure_never_emits_a_passing_receipt(self) -> None:
        for failed_release in ("lease", "cache"):
            with self.subTest(failed_release=failed_release), tempfile.TemporaryDirectory() as tmp:
                completed, receipt, operations, _sha = self.run_readiness(Path(tmp), failed_release=failed_release)

                self.assertNotEqual(completed.returncode, 0, completed.stderr)
                self.assertFalse(receipt["passed"])
                self.assertEqual(receipt["error"], "pre-tag-readiness authenticated cleanup failed")
                self.assertEqual([line.split()[0] for line in operations][-2:], ["lease-release", "cache-release"])

    def test_inherited_git_config_cannot_redirect_fixture_origin(self) -> None:
        git_config_override = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "remote.origin.url",
            "GIT_CONFIG_VALUE_0": "file:///nonexistent",
        }
        with patch.dict(os.environ, git_config_override, clear=False), tempfile.TemporaryDirectory() as tmp:
            completed, receipt, operations, _sha = self.run_readiness(Path(tmp))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(receipt["passed"])
        self.assertEqual([line.split()[0] for line in operations], [
            "cache-prepare", "lease-acquire", "harness", "lease-release", "cache-release",
        ])


if __name__ == "__main__":
    unittest.main()
