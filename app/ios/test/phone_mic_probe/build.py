#!/usr/bin/env python3
"""Build a separate, offline iPhone probe from production PhoneMic sources.

Build/sign only; never installs, launches, registers, or leases a device.
Requires an explicitly selected development profile and signing identity.
"""

import argparse
import hashlib
import json
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MIC = ROOT / "app/ios/Runner/PhoneMic"
BUNDLE_ID = "com.friend-app-with-wearable.ios12.development.micprobe"
SOURCES = [
    "PhoneMicController",
    "PhoneMicControllerSeams",
    "PhoneMicEventEmitter",
    "PhoneMicCaptureEngine",
    "PhoneMicConverterPipeline",
    "PhoneMicInterruptionMonitor",
    "PhoneMicPermissionGate",
    "PhoneMicSessionConfigurator",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--identity")
    parser.add_argument(
        "--check", action="store_true", help="Compile native probe without signing, a device, or retained build output"
    )
    args = parser.parse_args()
    if args.check:
        if args.output or args.profile or args.identity:
            parser.error("--check takes no output/profile/identity")
        with tempfile.TemporaryDirectory(prefix="omi-probe-compile-") as directory:
            build(parser, args, Path(directory))
        subprocess.run([sys.executable, str(HERE.parent / "audio_interruption_driver/build.py"), "--check"], check=True)
        print("Native microphone/wearable probe compile passed (no signing or device)")
    else:
        if not (args.output and args.profile and args.identity):
            parser.error("signed builds require --output, --profile, and --identity")
        build(parser, args, args.output.resolve())


def build(parser, args, output):
    output.mkdir(parents=True, exist_ok=True)
    app = output / "OmiMicProbe.app"
    if app.exists():
        parser.error("output already contains OmiMicProbe.app; choose a fresh output directory")
    if not args.check:
        profile = plistlib.loads(subprocess.check_output(["security", "cms", "-D", "-i", str(args.profile)]))
        entitlement = profile["Entitlements"]
        if not entitlement.get("get-task-allow") or not profile.get("ProvisionedDevices"):
            parser.error("a development profile with provisioned devices is required")
        team = profile["TeamIdentifier"][0]
        full_id = team + "." + BUNDLE_ID
        allowed = entitlement["application-identifier"]
        if not (allowed == full_id or (allowed.endswith(".*") and full_id.startswith(allowed[:-1]))):
            parser.error("profile does not cover the separate probe bundle id")
    generated = MIC / "PhoneMicPigeon.g.swift"
    models = ROOT / "app/lib/services/devices/models.dart"
    paths = [MIC / (name + ".swift") for name in SOURCES] + [HERE / "Probe.swift", HERE / "WearableProbe.swift"]
    inputs = paths + [generated, models, Path(__file__).resolve()]
    # Pin before extracting generated types/constants as well as compiling.
    # An agent may edit this shared checkout while swiftc is running.
    input_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    text = generated.read_text()
    blocks = []
    for pattern in [
        r"enum PhoneMicCaptureState: Int \{.*?\n\}",
        r"enum PhoneMicCaptureMode: Int \{.*?\n\}",
        r"final class PhoneMicPigeonError: Error \{.*?\n\}",
    ]:
        match = re.search(pattern, text, re.S)
        if match is None:
            parser.error("Pigeon contract extraction drift; inspect generated definitions")
        blocks.append(match[0])
    stub = output / "PigeonTypes.swift"
    stub.write_text("import Foundation\n" + "\n\n".join(blocks) + "\n")
    uuid_constants = []
    for dart_name, swift_name in [("omiServiceUuid", "service"), ("audioDataStreamCharacteristicUuid", "audio")]:
        value = re.search(r"const String " + dart_name + r" = '([0-9a-f-]+)';", models.read_text())
        if value is None:
            parser.error("BLE UUID extraction drift")
        uuid_constants.append(f'    static let {swift_name} = "{value[1]}"')
    ble_constants = output / "BleUUIDs.swift"
    ble_constants.write_text("enum ProbeBleUUIDs {\n" + "\n".join(uuid_constants) + "\n}\n")
    app.mkdir()
    sdk = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True).strip()
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
            *map(str, paths),
            str(stub),
            str(ble_constants),
            "-o",
            str(app / "OmiMicProbe"),
        ],
        check=True,
    )
    if input_hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}:
        raise RuntimeError("Probe inputs changed during compilation; rebuild before attributing this artifact")
    if git_sha != subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip():
        raise RuntimeError("Source commit changed during compilation; rebuild before attributing this artifact")
    if args.check:
        return
    plist = {
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleName": "OmiMicProbe",
        "CFBundleDisplayName": "Omi Mic Probe",
        "CFBundleExecutable": "OmiMicProbe",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1.0",
        "MinimumOSVersion": "16.0",
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "UIDeviceFamily": [1],
        "UILaunchScreen": {},
        "UIApplicationSceneManifest": {
            "UIApplicationSupportsMultipleScenes": False,
            "UISceneConfigurations": {"UIWindowSceneSessionRoleApplication": [{"UISceneConfigurationName": "Probe"}]},
        },
        "UIBackgroundModes": ["audio", "bluetooth-central"],
        "NSBluetoothAlwaysUsageDescription": "Test reconnect and audio packet delivery from your selected Omi wearable. Audio is discarded.",
        "NSMicrophoneUsageDescription": "Count audio frames to test recording recovery. Audio is discarded and never uploaded.",
    }
    (app / "Info.plist").write_bytes(plistlib.dumps(plist))
    shutil.copyfile(args.profile, app / "embedded.mobileprovision")
    signing = {"application-identifier": full_id, "com.apple.developer.team-identifier": team, "get-task-allow": True}
    entitlements = output / "entitlements.plist"
    entitlements.write_bytes(plistlib.dumps(signing))
    manifest = {
        "schema": "phone-mic-probe-build/v1",
        "bundle_id": BUNDLE_ID,
        "git_sha": git_sha,
        "inputs": input_hashes,
        "unsigned_binary_sha256": hashlib.sha256((app / "OmiMicProbe").read_bytes()).hexdigest(),
        "xcode": subprocess.check_output(["xcodebuild", "-version"], text=True).strip(),
        "mode": "optimized-native",
        "scopes": ["native-stream-only", "corebluetooth-radio-only"],
    }
    (app / "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    subprocess.run(
        ["codesign", "--force", "--sign", args.identity, "--entitlements", str(entitlements), str(app)], check=True
    )
    subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True)
    files = {
        str(p.relative_to(app)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(app.rglob("*"))
        if p.is_file()
    }
    signed = {
        "schema": "phone-mic-probe-artifact/v1",
        "bundle_id": BUNDLE_ID,
        "source_git_sha": manifest["git_sha"],
        "files": files,
        "tree_sha256": hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
    (output / "signed-artifact.json").write_text(json.dumps(signed, indent=2) + "\n")
    print(app)


if __name__ == "__main__":
    main()
