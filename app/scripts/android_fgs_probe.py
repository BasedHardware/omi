#!/usr/bin/env python3
"""Exercise the real sync service on an isolated Android 16 emulator, without auth."""

import argparse
import json
import os
import shutil
from pathlib import Path
import subprocess
import time

from android_emulator import sha256_file

APP = Path(__file__).resolve().parents[1]
PACKAGE = "com.omi.fgsprobe"
MODES = ("empty", "burst", "restart", "orphan-stop", "background-stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gradle", default=str(APP / "android/gradlew"))
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    if not Path(args.gradle).is_file() and shutil.which(args.gradle) is None:
        parser.error("Gradle executable is missing. Pass --gradle /path/to/gradle; see the probe README.")
    sdk = Path(os.environ.get("ANDROID_HOME", str(Path.home() / "Library/Android/sdk")))
    adb = [str(sdk / "platform-tools/adb"), "-s", args.serial]

    def device(*command):
        for attempt in range(2):
            result = subprocess.run([*adb, *command], text=True, capture_output=True, timeout=20)
            if result.returncode == 0:
                return result.stdout.strip()
            if attempt == 0 and ("device offline" in result.stderr or "device not found" in result.stderr):
                subprocess.run([*adb, "wait-for-device"], check=True, timeout=15)
                continue
            raise RuntimeError(f"ADB {command} failed ({result.returncode}): {result.stderr.strip()}")

    if device("shell", "getprop", "ro.kernel.qemu") != "1":
        raise SystemExit("This probe requires an isolated emulator.")
    if int(device("shell", "getprop", "ro.build.version.sdk")) < 36:
        raise SystemExit("The reproduced cancellation failure requires Android 16+.")
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    boot_id = device("shell", "cat", "/proc/sys/kernel/random/boot_id")
    args.output.mkdir(parents=True, exist_ok=True)
    receipt_path = args.output / "receipt.json"
    receipt_path.unlink(missing_ok=True)
    project = APP / "integration_test/android_fgs_probe"
    env = dict(os.environ, ANDROID_HOME=str(sdk))
    subprocess.run(
        [args.gradle, "-p", str(project), "assembleDebug", "--console=plain"],
        env=env,
        check=True,
        timeout=600,
    )
    apk = project / "build/outputs/apk/debug/fgs-probe-debug.apk"
    device("install", "-r", str(apk))
    results = []
    artifact_hash = sha256_file(apk)
    receipt = {
        "schema_version": 1,
        "kind": "android-fgs-lifecycle",
        "passed": False,
        "source_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "artifact_sha256": artifact_hash,
        "serial": args.serial,
        "boot_id": boot_id,
        "api_level": int(device("shell", "getprop", "ro.build.version.sdk")),
        "rounds": args.rounds,
        "cases": results,
    }
    try:
        for round_number in range(args.rounds):
            for mode in MODES:
                device("shell", "am", "force-stop", PACKAGE)
                device("logcat", "-c")
                device(
                    "shell",
                    "am",
                    "start",
                    "-n",
                    f"{PACKAGE}/.ProbeActivity",
                    "--es",
                    "mode",
                    mode,
                )
                active_verified = mode not in ("burst", "restart")
                # Android enforces its own foreground deadline. Give the
                # emulator enough bounded wall time to deliver Activity.onStop
                # and emit the terminal marker on a busy CI host.
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    log = device(
                        "logcat",
                        "-d",
                        "-v",
                        "threadtime",
                        "-s",
                        "FGS_PROBE",
                        "AndroidRuntime",
                        "SyncTransfer.FgService",
                    )
                    if not active_verified and f"ACTIVE mode={mode}" in log:
                        active = device("shell", "dumpsys", "activity", "services", PACKAGE)
                        active_power = (
                            device(
                                "shell",
                                "dumpsys power | sed -n '/^Wake Locks:/,/^Suspend Blockers:/p'",
                            )
                            .split("Wake Locks:", 1)[1]
                            .split("Suspend Blockers:", 1)[0]
                        )
                        active_verified = "isForeground=true" in active and "omi:sync-transfer" in active_power
                        if not active_verified:
                            raise SystemExit("A queued stop terminated the later active transfer.")
                    if f"SURVIVED mode={mode}" in log or "FATAL EXCEPTION" in log:
                        break
                    time.sleep(0.5)
                (args.output / f"{round_number}-{mode}.log").write_text(log)
                services = device("shell", "dumpsys", "activity", "services", PACKAGE)
                power = device(
                    "shell",
                    "dumpsys power | sed -n '/^Wake Locks:/,/^Suspend Blockers:/p'",
                )
                notifications = device("shell", "cmd", "notification", "list")
                passed = (
                    device("shell", "cat", "/proc/sys/kernel/random/boot_id") == boot_id
                    and active_verified
                    and "Foreground promotion accepted" in log
                    and (mode == "orphan-stop" or "ACCEPTED" in log)
                    and (mode != "background-stop" or "BACKGROUND_STOP" in log)
                    and f"SURVIVED mode={mode}" in log
                    and "FATAL EXCEPTION" not in log
                    and "ServiceRecord{" not in services
                    and "omi:sync-transfer" not in power.split("Wake Locks:", 1)[1].split("Suspend Blockers:", 1)[0]
                    and f"|{PACKAGE}|" not in notifications
                )
                results.append({"round": round_number, "mode": mode, "passed": passed})
                (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
                print(results[-1], flush=True)
                if not passed:
                    raise SystemExit("Native foreground-service regression; see probe logs.")
    finally:
        try:
            device("shell", "am", "force-stop", PACKAGE)
            receipt["passed"] = len(results) == args.rounds * len(MODES) and all(case["passed"] for case in results)
        finally:
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"PASS: {len(results)} cold launches; no crash, service, notification, or wake-lock leak.")


if __name__ == "__main__":
    main()
