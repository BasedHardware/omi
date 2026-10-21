#!/usr/bin/env python3
"""Build a separate offline playback app for real microphone interruptions."""

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BUNDLE = "com.friend-app-with-wearable.ios12.development.interruptiondriver"


def build(output, profile=None, identity=None):
    output.mkdir(parents=True, exist_ok=True)
    app = output / "OmiAudioInterruption.app"
    app.mkdir()  # Never overwrite an attributed artifact.
    entitlements = None
    if profile:
        value = plistlib.loads(subprocess.check_output(["security", "cms", "-D", "-i", str(profile)]))
        entitlements = value["Entitlements"]
        allowed = entitlements["application-identifier"]
        full_id = value["TeamIdentifier"][0] + "." + BUNDLE
        if not (entitlements.get("get-task-allow") and value.get("ProvisionedDevices")):
            raise ValueError("development profile required")
        if not (allowed == full_id or (allowed.endswith(".*") and full_id.startswith(allowed[:-1]))):
            raise ValueError("profile does not cover separate driver bundle")
    input_hashes = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                    for name in ("Driver.swift", "build.py")}
    sdk = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True).strip()
    executable = app / "OmiAudioInterruption"
    subprocess.run(
        [
            "xcrun",
            "--sdk",
            "iphoneos",
            "swiftc",
            "-sdk",
            sdk,
            "-target",
            "arm64-apple-ios16.0",
            "-O",
            "-parse-as-library",
            str(HERE / "Driver.swift"),
            "-o",
            str(executable),
        ],
        check=True,
    )
    if input_hashes != {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                       for name in input_hashes}:
        raise RuntimeError("Driver inputs changed during compilation; rebuild before attributing this artifact")
    manifest = {
        "schema": "omi-audio-interruption-build/v1",
        "inputs": input_hashes,
        "unsigned_executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    (app / "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    info = {
        "CFBundleIdentifier": BUNDLE,
        "CFBundleName": "OmiAudioInterruption",
        "CFBundleDisplayName": "Omi Audio Interrupter",
        "NSMicrophoneUsageDescription": "Briefly take microphone ownership to test Omi capture recovery; audio is discarded.",
        "CFBundleExecutable": "OmiAudioInterruption",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1.0",
        "MinimumOSVersion": "16.0",
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "UIDeviceFamily": [1],
        "UILaunchScreen": {},
        "UIBackgroundModes": ["audio", "voip"],
        "UIApplicationSceneManifest": {
            "UIApplicationSupportsMultipleScenes": False,
            "UISceneConfigurations": {
                "UIWindowSceneSessionRoleApplication": [
                    {
                        "UISceneConfigurationName": "Default",
                        "UISceneDelegateClassName": "OmiAudioInterruption.SceneDelegate",
                    }
                ]
            },
        },
    }
    (app / "Info.plist").write_bytes(plistlib.dumps(info))
    if not profile:
        return
    shutil.copyfile(profile, app / "embedded.mobileprovision")
    signing = {
        "application-identifier": full_id,
        "com.apple.developer.team-identifier": value["TeamIdentifier"][0],
        "get-task-allow": True,
        "keychain-access-groups": [full_id],
    }
    entitlement_path = output / "entitlements.plist"
    entitlement_path.write_bytes(plistlib.dumps(signing))
    subprocess.run(
        ["codesign", "--force", "--sign", identity, "--entitlements", str(entitlement_path), str(app)], check=True
    )
    subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True)
    hashes = {
        str(p.relative_to(app)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(app.rglob("*"))
        if p.is_file()
    }
    (output / "signed-artifact.json").write_text(json.dumps({"bundle_id": BUNDLE, "files": hashes}, indent=2) + "\n")
    print(app)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--identity")
    args = parser.parse_args()
    if args.check:
        if args.output or args.profile or args.identity:
            parser.error("--check takes no signing/output arguments")
        with tempfile.TemporaryDirectory(prefix="omi-interruption-compile-") as directory:
            build(Path(directory))
        subprocess.run([sys.executable, str(HERE / "test_driver.py")], check=True)
        print("Audio interruption driver compile and evidence-oracle tests passed")
    else:
        if not all((args.output, args.profile, args.identity)):
            parser.error("signed builds require --output, --profile, --identity")
        build(args.output, args.profile, args.identity)


if __name__ == "__main__":
    main()
