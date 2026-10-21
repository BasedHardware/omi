#!/usr/bin/env python3
"""Behavior tests for .github/scripts/install_android_ndk.py.

The script owns the corrupt-NDK-archive recovery (purge the partial NDK and
sdkmanager temp state, retry once, per-attempt timeout), so its behavior —
not just its presence in the workflow — is the guard for the 2026-10-21
"Error on ZipFile unknown archive" flake class (runs 39506049904,
39626150998). Each test drives the real CLI against a fake sdkmanager.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "install_android_ndk.py"
NDK_VERSION = "28.2.13676358"

# Fake sdkmanager: writes a valid NDK unless $ANDROID_HOME/.fake-fail-remaining
# says otherwise, counting down across invocations. A forced failure removes
# source.properties but leaves partial state, like a corrupt archive download.
FAKE_SDKMANAGER = """\
    #!/bin/sh
    mkdir -p "$ANDROID_HOME"
    echo invoked >> "$ANDROID_HOME/.fake-invocations"
    ver=${1#ndk;}
    ndk_dir="$ANDROID_HOME/ndk/$ver"
    mkdir -p "$ndk_dir"
    printf 'Pkg.Desc = Android NDK\\nPkg.Revision = %s\\n' "$ver" > "$ndk_dir/source.properties"
    count_file="$ANDROID_HOME/.fake-fail-remaining"
    if [ -f "$count_file" ]; then
      remaining=$(cat "$count_file")
      if [ "$remaining" -gt 0 ]; then
        echo "$((remaining - 1))" > "$count_file"
        rm "$ndk_dir/source.properties"
        touch "$ndk_dir/.partial-archive" "$ANDROID_HOME/.temp/partial-download.zip"
        echo "fake sdkmanager: forced failure ($remaining remaining)" >&2
        exit 1
      fi
    fi
    exit 0
    """

# Variant whose first invocation hangs past the per-attempt timeout instead of
# failing fast: the install must still retry and recover. `exec sleep` keeps
# the hang in the direct child so the timeout kill closes the output pipes.
FAKE_HANGING_SDKMANAGER = """\
    #!/bin/sh
    mkdir -p "$ANDROID_HOME"
    echo invoked >> "$ANDROID_HOME/.fake-invocations"
    count_file="$ANDROID_HOME/.fake-fail-remaining"
    if [ -f "$count_file" ] && [ "$(cat "$count_file")" -gt 0 ]; then
      echo 0 > "$count_file"
      exec sleep 30
    fi
    ver=${1#ndk;}
    ndk_dir="$ANDROID_HOME/ndk/$ver"
    mkdir -p "$ndk_dir"
    printf 'Pkg.Desc = Android NDK\\nPkg.Revision = %s\\n' "$ver" > "$ndk_dir/source.properties"
    exit 0
    """


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

    def run_installer(self, *extra_args: str, env_android_home: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.pop("ANDROID_HOME", None)
        if env_android_home:
            env["ANDROID_HOME"] = str(self.android_home)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--ndk-version", NDK_VERSION, *extra_args],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def seed_failures(self, count: int) -> None:
        self.android_home.mkdir(parents=True, exist_ok=True)
        (self.android_home / ".fake-fail-remaining").write_text(str(count), encoding="utf-8")

    def invocations(self) -> int:
        log = self.android_home / ".fake-invocations"
        if not log.exists():
            return 0
        return len(log.read_text(encoding="utf-8").splitlines())

    def ndk_dir(self) -> Path:
        return self.android_home / "ndk" / NDK_VERSION

    def test_present_ndk_skips_sdkmanager_entirely(self) -> None:
        source = self.ndk_dir() / "source.properties"
        source.parent.mkdir(parents=True)
        source.write_text(f"Pkg.Desc = Android NDK\nPkg.Revision = {NDK_VERSION}\n", encoding="utf-8")
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("already present", result.stdout)
        self.assertEqual(0, self.invocations())

    def test_first_attempt_success_never_retries(self) -> None:
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("installed on first attempt", result.stdout)
        self.assertEqual(1, self.invocations())
        self.assertIn(f"Pkg.Revision = {NDK_VERSION}", (self.ndk_dir() / "source.properties").read_text())

    def test_corrupt_first_attempt_is_purged_and_retried_once(self) -> None:
        self.seed_failures(1)
        (self.android_home / ".temp").mkdir(parents=True)
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("installed on retry", result.stdout)
        self.assertEqual(2, self.invocations())
        self.assertFalse((self.ndk_dir() / ".partial-archive").exists())
        self.assertFalse((self.android_home / ".temp").exists())
        self.assertIn(f"Pkg.Revision = {NDK_VERSION}", (self.ndk_dir() / "source.properties").read_text())

    def test_double_failure_fails_after_exactly_one_retry(self) -> None:
        self.seed_failures(2)
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(1, result.returncode)
        self.assertEqual(2, self.invocations())
        self.assertIn("did not install after retry", result.stderr)

    def test_stale_revision_is_not_treated_as_installed(self) -> None:
        source = self.ndk_dir() / "source.properties"
        source.parent.mkdir(parents=True)
        source.write_text("Pkg.Desc = Android NDK\nPkg.Revision = 27.0.00000000\n", encoding="utf-8")
        result = self.run_installer("--sdkmanager", str(self.sdkmanager))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, self.invocations())

    def test_hung_attempt_times_out_and_recovers_on_retry(self) -> None:
        self.write_fake(self.sdkmanager, FAKE_HANGING_SDKMANAGER)
        self.seed_failures(1)
        result = self.run_installer("--sdkmanager", str(self.sdkmanager), "--attempt-timeout", "1")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("installed on retry", result.stdout)
        self.assertIn("exceeded", result.stderr)
        self.assertEqual(2, self.invocations())

    def test_missing_android_home_is_a_usage_error(self) -> None:
        result = self.run_installer("--sdkmanager", str(self.sdkmanager), env_android_home=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("ANDROID_HOME", result.stderr)

    def test_explicit_android_home_overrides_environment(self) -> None:
        source = self.ndk_dir() / "source.properties"
        source.parent.mkdir(parents=True)
        source.write_text(f"Pkg.Revision = {NDK_VERSION}\n", encoding="utf-8")
        result = self.run_installer(
            "--sdkmanager", str(self.sdkmanager), "--android-home", str(self.android_home)
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
