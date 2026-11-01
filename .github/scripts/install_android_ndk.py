#!/usr/bin/env python3
"""Install the pinned Android NDK before Gradle runs, with one retry.

The Android Gradle Plugin auto-installs a missing NDK inside Gradle
configuration with no retry and no integrity fallback, so one truncated
dl.google.com response fails the whole job before any app code runs:
"Error on ZipFile unknown archive" (job runs 39506049904 and 39626150998
died 5 s into a download that takes ~22 s when healthy). Installing the
NDK explicitly before Gradle lets this script verify the install, purge
partial state, and retry once. Called by the three Gradle-configuring
jobs in mobile-app-checks.yml; asserted by
.github/scripts/test_mobile_ci_infra_guards.py.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

# A healthy download + extract takes ~22 s. Two full attempts must still fit
# inside the 25-minute Android Compile Smoke and JVM ceilings next to their
# ~13 / ~9 minute p50 bodies, so the cap is minutes, not the job budget:
# 2 x 240 s = 8 min worst case, which also leaves ~3 MB/s for a slow CDN day.
DEFAULT_ATTEMPT_TIMEOUT_SECONDS = 240


def ndk_is_installed(ndk_dir: Path, version: str) -> bool:
    try:
        properties = (ndk_dir / "source.properties").read_text(encoding="utf-8")
    except OSError:
        return False
    return f"Pkg.Revision = {version}" in properties


def wait_for_group_exit(pgid: int, timeout: float = 10.0) -> None:
    """Block until every member of a SIGKILLed process group is gone.

    ``Popen.wait`` reaps only the wrapper; a worker still draining out of the
    run queue keeps the group alive, and the retry's purge must not race a
    dying writer. Signal 0 probes existence; zombies count until reaped, so
    the wait is bounded rather than open-ended.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)


def run_sdkmanager(sdkmanager: Path, android_home: Path, version: str, timeout: float) -> bool:
    # --sdk_root keeps sdkmanager writing under the same root this script
    # verifies and purges, whatever ANDROID_HOME the wrapper would derive.
    command = [str(sdkmanager), f"--sdk_root={android_home}", f"ndk;{version}"]
    print(f"+ {' '.join(command)}", flush=True)
    # The cmdline-tools sdkmanager is a shell wrapper around a Java child it
    # does not exec. A timeout must kill the whole process group, and the
    # purge below must wait for that group to empty, or the extractor keeps
    # writing into the tree the retry is about to purge.
    process = subprocess.Popen(command, start_new_session=True)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"sdkmanager attempt exceeded {timeout:.0f}s; killing its process group", file=sys.stderr)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        wait_for_group_exit(process.pid)
        return False
    return process.returncode == 0


def install(sdkmanager: Path, android_home: Path, ndk_dir: Path, version: str, timeout: float) -> bool:
    """Install `ndk;<version>` once; a zero exit alone is not success."""
    if not run_sdkmanager(sdkmanager, android_home, version, timeout):
        return False
    return ndk_is_installed(ndk_dir, version)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preinstall a pinned Android NDK with one retry.")
    parser.add_argument("--ndk-version", required=True, help="e.g. 28.2.13676358")
    parser.add_argument(
        "--android-home",
        default=os.environ.get("ANDROID_HOME"),
        help="Android SDK root (default: $ANDROID_HOME); passed to sdkmanager as --sdk_root",
    )
    parser.add_argument(
        "--sdkmanager",
        default=None,
        help="sdkmanager path (default: <android-home>/cmdline-tools/latest/bin/sdkmanager)",
    )
    parser.add_argument(
        "--attempt-timeout",
        type=float,
        default=DEFAULT_ATTEMPT_TIMEOUT_SECONDS,
        help="per-attempt sdkmanager timeout in seconds (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    if not args.android_home:
        print("FAIL: --android-home or $ANDROID_HOME is required", file=sys.stderr)
        return 2
    android_home = Path(args.android_home)
    sdkmanager = (
        Path(args.sdkmanager)
        if args.sdkmanager
        else android_home / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
    )
    ndk_dir = android_home / "ndk" / args.ndk_version

    if ndk_is_installed(ndk_dir, args.ndk_version):
        print(f"Android NDK {args.ndk_version} already present at {ndk_dir}; skipping install")
        return 0

    if install(sdkmanager, android_home, ndk_dir, args.ndk_version, args.attempt_timeout):
        print(f"Android NDK {args.ndk_version} installed on first attempt")
        return 0

    print(
        "::warning title=Android NDK install retry::first attempt failed or left no usable "
        f"NDK; purging {ndk_dir} and {android_home / '.temp'} and retrying once"
    )
    shutil.rmtree(ndk_dir, ignore_errors=True)
    shutil.rmtree(android_home / ".temp", ignore_errors=True)
    if install(sdkmanager, android_home, ndk_dir, args.ndk_version, args.attempt_timeout):
        print(f"Android NDK {args.ndk_version} installed on retry")
        return 0

    print(f"FAIL: Android NDK {args.ndk_version} did not install after retry", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
