#!/usr/bin/env python3
"""Fail closed unless an iOS dogfood app is a signed standalone AOT artifact."""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"iOS dogfood artifact verification FAILED: {message}")


def load_plist(path: Path) -> dict[str, object]:
    if not path.is_file():
        fail(f"missing {path}")
    try:
        with path.open("rb") as stream:
            value = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException) as error:
        fail(f"invalid plist {path}: {error}")
    if not isinstance(value, dict):
        fail(f"plist root is not a dictionary: {path}")
    return value


def verify(
    app: Path,
    bundle_id: str,
    application_id: str,
    codesign: str,
) -> None:
    if not app.is_dir():
        fail(f"app does not exist: {app}")

    info = load_plist(app / "Info.plist")
    if info.get("CFBundleIdentifier") != bundle_id:
        fail(f"unexpected bundle identifier {info.get('CFBundleIdentifier')!r}")

    firebase = load_plist(app / "GoogleService-Info.plist")
    if firebase.get("PROJECT_ID") != "based-hardware":
        fail("artifact is not configured for the canonical Firebase project")

    jit_kernel = app / "Frameworks/App.framework/flutter_assets/kernel_blob.bin"
    if jit_kernel.exists():
        fail("refusing Flutter debug/JIT artifact; unattended dogfood requires profile/AOT")

    try:
        subprocess.run(
            [codesign, "--verify", "--deep", "--strict", str(app)],
            check=True,
            capture_output=True,
            text=True,
        )
        entitlement_result = subprocess.run(
            [codesign, "-d", "--entitlements", ":-", str(app)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        fail(f"artifact signature is invalid: {error}")

    entitlements = entitlement_result.stdout + entitlement_result.stderr
    if application_id not in entitlements:
        fail("artifact has the wrong application identifier")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--codesign", default="codesign")
    args = parser.parse_args()
    verify(args.app, args.bundle_id, args.application_id, args.codesign)
    print("iOS dogfood artifact verification: PASS (signed standalone AOT app)")


if __name__ == "__main__":
    main()
