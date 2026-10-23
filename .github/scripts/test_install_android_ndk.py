#!/usr/bin/env python3
"""Behavior tests for .github/scripts/install_android_ndk.py.

The script owns the corrupt-NDK-archive recovery (purge the partial NDK and
sdkmanager temp state, retry once, per-attempt timeout that kills the whole
sdkmanager process group), so its behavior — not just its presence in the
workflow — is the guard for the 2026-10-21 "Error on ZipFile unknown
archive" flake class (runs 39506049904, 39626150998). Each test drives the
real CLI against a fake sdkmanager.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "install_android_ndk.py"
NDK_VERSION = "28.2.13676358"

# Fake sdkmanager: honours --sdk_root like the real wrapper, writes a valid NDK
# unless <root>/.fake-fail-remaining says otherwise (counting down across
# invocations), and records every invocation's argv. A forced failure removes
# source.properties but leaves partial state, like a corrupt archive download.
FAKE_SDKMANAGER = """\
    #!/bin/sh
    root="$ANDROID_HOME"
    ver=""
    for arg in "$@"; do
      case "$arg" in
        --sdk_root=*) root="${arg#--sdk_root=}" ;;
        'ndk;'*) ver="${arg#ndk;}" ;;
      esac
    done
    mkdir -p "$root"
    echo "$*" >> "$root/.fake-invocations"
    ndk_dir="$root/ndk/$ver"
    mkdir -p "$ndk_dir"
    printf 'Pkg.Desc = Android NDK\\nPkg.Revision = %s\\n' "$ver" > "$ndk_dir/source.properties"
    count_file="$root/.fake-fail-remaining"
    if [ -f "$count_file" ]; then
      remaining=$(cat "$count_file")
      if [ "$remaining" -gt 0 ]; then
        echo "$((remaining - 1))" > "$count_file"
        rm "$ndk_dir/source.properties"
        mkdir -p "$root/.temp"
        touch "$ndk_dir/.partial-archive" "$root/.temp/partial-download.zip"
        echo "fake sdkmanager: forced failure ($remaining remaining)" >&2
        exit 1
      fi
    fi
    exit 0
    """

# Variant whose first invocation hangs past the per-attempt timeout. Like the
# real cmdline-tools wrapper it does NOT exec its worker: the hang lives in a
# background child whose pid is recorded, and the retry invocation records
# whether that worker still exists, so the test can prove the installer killed
# the whole process group and waited for it before purging and retrying.
FAKE_HANGING_SDKMANAGER = """\
    #!/bin/sh
    root="$ANDROID_HOME"
    ver=""
    for arg in "$@"; do
      case "$arg" in
        --sdk_root=*) root="${arg#--sdk_root=}" ;;
        'ndk;'*) ver="${arg#ndk;}" ;;
      esac
    done
    mkdir -p "$root"
    echo "$*" >> "$root/.fake-invocations"
    count_file="$root/.fake-fail-remaining"
    if [ -f "$count_file" ] && [ "$(cat "$count_file")" -gt 0 ]; then
      echo 0 > "$count_file"
      sleep 300 &
      echo $! > "$root/.fake-child-pid"
      wait
      exit 1
    fi
    if [ -f "$root/.fake-child-pid" ]; then
      if kill -0 "$(cat "$root/.fake-child-pid")" 2>/dev/null; then
        echo alive > "$root/.fake-child-at-retry"
      else
        echo gone > "$root/.fake-child-at-retry"
      fi
    fi
    ndk_dir="$root/ndk/$ver"
    mkdir -p "$ndk_dir"
    printf 'Pkg.Desc = Android NDK\\nPkg.Revision = %s\\n' "$ver" > "$ndk_dir/source.properties"
    exit 0
    """


def pid_is_gone(pid: int, wait_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        # A SIGKILLed orphan stays a zombie until init reaps it; keep polling.
        time.sleep(0.05)
    return False


class InstallAndroidNdkTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.android_home = root / "android-sdk"
        self.sdkmanager = root / "fake-bin" / "sdkmanager"
        self.write_fake(self.sdkmanager, FAKE_SDKMANAGER)

    def write_fake(self, path: Path, script: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(script), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def run_installer(
        self, *extra_args: str, env_android_home: str | None | bool = True
    ) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.pop("ANDROID_HOME", None)
        if env_android_home is True:
            env["ANDROID_HOME"] = str(self.android_home)
        elif isinstance(env_android_home, str):
            env["ANDROID_HOME"] = env_android_home
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--ndk-version", NDK_VERSION, *extra_args],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def seed_failures(self, count: int, root: Path | None = None) -> None:
        root = root or self.android_home
        root.mkdir(parents=True, exist_ok=True)
        (root / ".fake-fail-remaining").write_text(str(count), encoding="utf-8")

    def invocations(self, root: Path | None = None) -> list[str]:
        log = (root or self.android_home) / ".fake-invocations"
        if not log.exists():
            return []
        return log.read_text(encoding="utf-8").splitlines()

    def ndk_dir(self, root: Path | None = None) -> Path:
        return (root or self.android_home) / "ndk" / NDK_VERSION

    def write_installed_ndk(self, root: Path | None = None, revision: str = NDK_VERSION) -> None:
        source = self.ndk_dir(root) / "source.properties"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"Pkg.Desc = Android NDK\nPkg.Revision = {revision}\n", encoding="utf-8")

    def test_present_ndk_skips_sdkmanager_entirely(self) -> None:
        self.write_installed_ndk()
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("already present", result.stdout)
        self.assertEqual([], self.invocations())

    def test_first_attempt_success_never_retries_and_pins_sdk_root(self) -> None:
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("installed on first attempt", result.stdout)
        self.assertEqual([f"--sdk_root={self.android_home} ndk;{NDK_VERSION}"], self.invocations())
        self.assertIn(f"Pkg.Revision = {NDK_VERSION}", (self.ndk_dir() / "source.properties").read_text())

    def test_corrupt_first_attempt_is_purged_and_retried_once(self) -> None:
        self.seed_failures(1)
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("installed on retry", result.stdout)
        self.assertEqual(2, len(self.invocations()))
        self.assertFalse((self.ndk_dir() / ".partial-archive").exists())
        self.assertFalse((self.android_home / ".temp").exists())
        self.assertIn(f"Pkg.Revision = {NDK_VERSION}", (self.ndk_dir() / "source.properties").read_text())

    def test_double_failure_fails_after_exactly_one_retry(self) -> None:
        self.seed_failures(2)
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(1, result.returncode)
        self.assertEqual(2, len(self.invocations()))
        self.assertIn("did not install after retry", result.stderr)

    def test_stale_revision_is_not_treated_as_installed(self) -> None:
        self.write_installed_ndk(revision="27.0.00000000")
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, len(self.invocations()))

    def test_hung_attempt_kills_the_whole_process_group_then_retries(self) -> None:
        self.write_fake(self.sdkmanager, FAKE_HANGING_SDKMANAGER)
        self.seed_failures(1)
        result = self.run_installer("--sdkmanager", str(self.sdkmanager), "--attempt-timeout", "1")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("installed on retry", result.stdout)
        self.assertIn("killing its process group", result.stderr)
        self.assertEqual(2, len(self.invocations()))
        child_pid = int((self.android_home / ".fake-child-pid").read_text().strip())
        self.assertTrue(
            pid_is_gone(child_pid),
            f"sdkmanager's non-exec'd worker {child_pid} survived the timeout; it would keep "
            "writing into the tree the retry purges",
        )
        self.assertEqual(
            "gone",
            (self.android_home / ".fake-child-at-retry").read_text().strip(),
            "the retry started while the killed worker still existed; the purge must wait "
            "for the whole process group to exit first",
        )

    def test_missing_android_home_is_a_usage_error(self) -> None:
        result = self.run_installer("--sdkmanager", str(self.sdkmanager), env_android_home=None)
        self.assertEqual(2, result.returncode)
        self.assertIn("ANDROID_HOME", result.stderr)

    def test_explicit_android_home_wins_over_a_divergent_environment(self) -> None:
        other_home = Path(self._tmp.name) / "other-sdk"
        result = self.run_installer(
            "--sdkmanager", str(self.sdkmanager), "--android-home", str(self.android_home),
            env_android_home=str(other_home),
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.ndk_dir() / "source.properties").exists())
        self.assertFalse(other_home.exists(), "sdkmanager wrote under $ANDROID_HOME instead of --sdk_root")
        self.assertEqual([f"--sdk_root={self.android_home} ndk;{NDK_VERSION}"], self.invocations())


if __name__ == "__main__":
    unittest.main()
