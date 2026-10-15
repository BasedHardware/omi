#!/usr/bin/env python3
"""Cold-launch an exact APK offline; require a rendered, healthy first-run screen."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import time
from xml.etree import ElementTree

from android_emulator import Emulator, sha256_file

PACKAGES = {"com.friend.ios", "com.friend.ios.dev"}


def apk_identity(apk, aapt):
    output = subprocess.run(
        [str(aapt), "dump", "badging", str(apk)], capture_output=True, text=True, check=True, timeout=30
    ).stdout
    match = re.search(r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'", output, re.M)
    if not match or match[1] not in PACKAGES:
        raise ValueError("APK must identify an Omi Android package and version.")
    return {"package": match[1], "version_code": match[2], "version_name": match[3]}


def assert_healthy(log, package, pid, current_pid, boot_id, current_boot, ui):
    if not pid or current_pid != pid or current_boot != boot_id:
        raise ValueError("Startup process died/restarted or emulator rebooted.")
    if f"Process: {package}, PID:" in log or f"ANR in {package}" in log or "Unhandled Exception" in log:
        raise ValueError("Startup reported a fatal exception or ANR.")
    if "get started" not in ui.lower():
        raise ValueError("First-run screen did not render; a surviving process alone is insufficient.")


def screen_from_instrumentation(dump, package):
    match = re.search(r"^INSTRUMENTATION_RESULT: screen=(.*?)(?=\nINSTRUMENTATION_[A-Z_]+:|\Z)", dump, re.M | re.S)
    if not match or not re.search(r"^INSTRUMENTATION_CODE: -1$", dump, re.M):
        raise ValueError("Accessibility instrumentation did not complete successfully.")
    ui = match[1].strip()
    root = ElementTree.fromstring(ui)
    if root.tag != "screen" or root.get("package") != package:
        raise ValueError("Accessibility screen does not belong to the launched app.")
    return ui


def run_smoke(device, apk, output, *, aapt, rounds=3, observe_seconds=20):
    if rounds < 1 or observe_seconds < 15:
        raise ValueError("Require at least one launch observed for at least 15 seconds.")
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / "receipt.json"
    receipt_path.unlink(missing_ok=True)
    identity = apk_identity(apk, aapt)
    package = identity["package"]
    boot_id = device.require_isolated()
    if not device.run("shell", "pm", "path", "com.omi.fgsprobe"):
        raise ValueError("Run android_fgs_probe.py first to install the accessibility probe.")
    if any(device.run("shell", "pm", "list", "packages", existing) for existing in sorted(PACKAGES)):
        raise ValueError("Use a fresh emulator without Omi installed; acceptance never clears existing account data.")
    artifact_hash = sha256_file(apk)
    receipt = {
        "schema_version": 1,
        "kind": "android-offline-startup",
        "passed": False,
        "runner_source_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "artifact_sha256": artifact_hash,
        **identity,
        "api_level": int(device.run("shell", "getprop", "ro.build.version.sdk")),
        "boot_id": boot_id,
        "serial": device.serial,
        "network": "none",
        "launches": [],
    }
    try:
        with device.offline():
            device.run("install", str(apk))
            try:
                for number in range(rounds):
                    device.run("shell", "am", "force-stop", package)
                    device.run("logcat", "-c")
                    device.require_offline()
                    launch = device.run("shell", "am", "start", "-W", "-n", f"{package}/com.friend.ios.MainActivity")
                    if "Status: ok" not in launch:
                        raise ValueError("Android did not accept the cold launch.")
                    pid = device.run("shell", f"pidof {package} || true")
                    start = time.monotonic()
                    ui = ""
                    while time.monotonic() - start < 60:
                        # The probe reads actual accessibility nodes directly;
                        # stock uiautomator dump waits for an idle event stream
                        # and stalls on the animated Flutter landing screen.
                        dump = device.run("shell", "am", "instrument", "-w", "com.omi.fgsprobe/.StartupScreenProbe")
                        (output / f"{number}-accessibility.log").write_text(dump)
                        ui = screen_from_instrumentation(dump, package)
                        if "get started" in ui.lower() and time.monotonic() - start >= observe_seconds:
                            break
                        if device.run("shell", f"pidof {package} || true") != pid:
                            break
                        time.sleep(1)
                    log = device.run(
                        "logcat", "-d", "-v", "threadtime", "-s", "AndroidRuntime", "ActivityManager", "flutter"
                    )
                    (output / f"{number}-startup.log").write_text(launch + "\n" + log)
                    (output / f"{number}-screen.xml").write_text(ui)
                    device.screenshot(output / f"{number}-screen.png")
                    device.require_offline()
                    assert_healthy(
                        log,
                        package,
                        pid,
                        device.run("shell", f"pidof {package} || true"),
                        boot_id,
                        device.run("shell", "cat", "/proc/sys/kernel/random/boot_id"),
                        ui,
                    )
                    receipt["launches"].append(
                        {"round": number, "passed": True, "observed_seconds": time.monotonic() - start}
                    )
            except Exception:
                # Preserve diagnostics even if UI dumping or launch itself
                # failed; absence of a successful screen is never a pass.
                (output / "failure.log").write_text(
                    device.run("logcat", "-d", "-v", "threadtime", "-s", "AndroidRuntime", "ActivityManager", "flutter")
                )
                raise
            finally:
                try:
                    device.run("shell", "am", "force-stop", package)
                finally:
                    device.run("uninstall", package)
        receipt["passed"] = True
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--aapt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    result = run_smoke(Emulator(args.serial), args.apk, args.output, aapt=args.aapt, rounds=args.rounds)
    print(
        f"PASS: {result['package']} {result['version_name']} ({result['version_code']}); {len(result['launches'])} offline cold launches"
    )


if __name__ == "__main__":
    main()
