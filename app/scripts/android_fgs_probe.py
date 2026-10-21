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
# Modes whose activity reports ACTIVE and then holds its stop until the runner
# broadcasts ACTION_VERIFIED, so the live-state check cannot race the teardown.
ACTIVE_MODES = ("burst", "restart")
ACTION_VERIFIED = "com.omi.fgsprobe.VERIFIED"
LOGCAT_TAGS = ("FGS_PROBE", "AndroidRuntime", "SyncTransfer.FgService")
# Android enforces its own foreground deadline. Give the emulator enough
# bounded wall time to deliver Activity.onStop and emit the terminal marker on
# a busy CI host.
CASE_DEADLINE_SECONDS = 60


def wake_locks(power):
    return power.split("Wake Locks:", 1)[1].split("Suspend Blockers:", 1)[0]


def snapshot(device):
    services = device("shell", "dumpsys", "activity", "services", PACKAGE)
    power = device("shell", "dumpsys power | sed -n '/^Wake Locks:/,/^Suspend Blockers:/p'")
    return services, power


def write_evidence(output, prefix, log, services, power, notifications=None):
    (output / f"{prefix}.log").write_text(log)
    (output / f"{prefix}-services.log").write_text(services + "\n")
    (output / f"{prefix}-power.log").write_text(power + "\n")
    if notifications is not None:
        (output / f"{prefix}-notifications.log").write_text(notifications + "\n")


def run_case(device, mode, round_number, output, boot_id, clock=time.monotonic, sleep=time.sleep):
    """Cold-launch one scenario and return its result row.

    Raises SystemExit when the activity reports ACTIVE but the service is not
    foreground with its wake lock; the live-state evidence is written first.
    """
    prefix = f"{round_number}-{mode}"
    device("shell", "am", "force-stop", PACKAGE)
    device("logcat", "-c")
    device("shell", "am", "start", "-n", f"{PACKAGE}/.ProbeActivity", "--es", "mode", mode)
    active_verified = mode not in ACTIVE_MODES
    deadline = clock() + CASE_DEADLINE_SECONDS
    log = ""
    while clock() < deadline:
        log = device("logcat", "-d", "-v", "threadtime", "-s", *LOGCAT_TAGS)
        if not active_verified and f"ACTIVE mode={mode}" in log:
            services, power = snapshot(device)
            active_verified = "isForeground=true" in services and "omi:sync-transfer" in wake_locks(power)
            write_evidence(output, f"{prefix}-active", log, services, power)
            if not active_verified:
                raise SystemExit(
                    f"{prefix}: the service was not foreground with its wake lock when the activity "
                    f"reported ACTIVE (a queued stop may have terminated the later transfer); "
                    f"see {prefix}-active-services.log and {prefix}-active-power.log."
                )
            device("shell", "am", "broadcast", "--receiver-foreground", "-a", ACTION_VERIFIED, "-p", PACKAGE)
        if f"SURVIVED mode={mode}" in log or "FATAL EXCEPTION" in log:
            break
        sleep(0.5)
    services, power = snapshot(device)
    notifications = device("shell", "cmd", "notification", "list")
    # Preserve the cleanup observations as well as survival logs. A failed
    # assertion otherwise loses the state needed to tell a real leak from an
    # emulator observation/timing problem.
    write_evidence(output, prefix, log, services, power, notifications)
    passed = (
        device("shell", "cat", "/proc/sys/kernel/random/boot_id") == boot_id
        and active_verified
        and "Foreground promotion accepted" in log
        and (mode == "orphan-stop" or "ACCEPTED" in log)
        and (mode != "background-stop" or "BACKGROUND_STOP" in log)
        and (mode not in ACTIVE_MODES or f"VERIFIED mode={mode}" in log)
        and "VERIFY_TIMEOUT" not in log
        and f"SURVIVED mode={mode}" in log
        and "FATAL EXCEPTION" not in log
        and "ServiceRecord{" not in services
        and "omi:sync-transfer" not in wake_locks(power)
        and f"|{PACKAGE}|" not in notifications
    )
    return {"round": round_number, "mode": mode, "passed": passed}


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
                results.append(run_case(device, mode, round_number, args.output, boot_id))
                (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
                print(results[-1], flush=True)
                if not results[-1]["passed"]:
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
