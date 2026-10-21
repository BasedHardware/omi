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
import subprocess
import sys
from pathlib import Path

DEFAULT_ATTEMPT_TIMEOUT_SECONDS = 600


def ndk_is_installed(ndk_dir: Path, version: str) -> bool:
    try:
        properties = (ndk_dir / "source.properties").read_text(encoding="utf-8")
    except OSError:
        return False
    return f"Pkg.Revision = {version}" in properties


def run_sdkmanager(sdkmanager: Path, version: str, timeout: float) -> bool:
    command = [str(sdkmanager), f"ndk;{version}"]
    print(f"+ {' '.join(command)}", flush=True)
    try:
        completed = subprocess.run(command, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"sdkmanager attempt exceeded {timeout:.0f}s", file=sys.stderr)
        return False
    return completed.returncode == 0


def install(sdkmanager: Path, ndk_dir: Path, version: str, timeout: float) -> bool:
    """Install `ndk;<version>` once; a zero exit alone is not success."""
    if not run_sdkmanager(sdkmanager, version, timeout):
        return False
    return ndk_is_installed(ndk_dir, version)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preinstall a pinned Android NDK with one retry.")
    parser.add_argument("--ndk-version", required=True, help="e.g. 28.2.13676358")
    parser.add_argument(
        "--android-home",
        default=os.environ.get("ANDROID_HOME"),
        help="Android SDK root (default: $ANDROID_HOME)",
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

    if install(sdkmanager, ndk_dir, args.ndk_version, args.attempt_timeout):
        print(f"Android NDK {args.ndk_version} installed on first attempt")
        return 0

    print(
        "::warning title=Android NDK install retry::first attempt failed or left no usable "
        f"NDK; purging {ndk_dir} and {android_home / '.temp'} and retrying once"
    )
    shutil.rmtree(ndk_dir, ignore_errors=True)
    shutil.rmtree(android_home / ".temp", ignore_errors=True)
    if install(sdkmanager, ndk_dir, args.ndk_version, args.attempt_timeout):
        print(f"Android NDK {args.ndk_version} installed on retry")
        return 0

    print(f"FAIL: Android NDK {args.ndk_version} did not install after retry", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
