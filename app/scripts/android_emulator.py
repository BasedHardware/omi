"""Bounded ADB and network isolation shared by Android acceptance runners."""

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import subprocess
import time


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Emulator:
    def __init__(self, serial):
        sdk = Path(os.environ.get("ANDROID_HOME", str(Path.home() / "Library/Android/sdk")))
        self.sdk = sdk
        self.serial = serial
        self.adb = [str(sdk / "platform-tools/adb"), "-s", serial]

    def run(self, *command):
        result = subprocess.run(self.adb + list(command), text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f"ADB {command[0]} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def require_isolated(self):
        if not self.serial.startswith("emulator-") or self.run("shell", "getprop", "ro.kernel.qemu") != "1":
            raise ValueError("Acceptance requires an isolated emulator; physical devices are refused.")
        if int(self.run("shell", "getprop", "ro.build.version.sdk")) < 36:
            raise ValueError("Acceptance requires Android 16/API 36 or newer.")
        return self.run("shell", "cat", "/proc/sys/kernel/random/boot_id")

    def require_offline(self):
        if "Active default network: none" not in self.run("shell", "dumpsys", "connectivity"):
            raise ValueError("Emulator still has a default network; refusing to launch app.")

    @contextmanager
    def offline(self):
        self.require_isolated()
        settings = {
            key: self.run("shell", "settings", "get", "global", key)
            for key in ("airplane_mode_on", "wifi_on", "mobile_data")
        }
        try:
            self.run("shell", "cmd", "connectivity", "airplane-mode", "enable")
            self.run("shell", "svc", "wifi", "disable")
            self.run("shell", "svc", "data", "disable")
            # Connectivity callbacks are asynchronous after svc/cmd return.
            # Wait for the observed boundary, never launch while still online.
            deadline = time.monotonic() + 10
            while True:
                try:
                    self.require_offline()
                    break
                except ValueError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.5)
            yield
        finally:
            # Restore every setting even if one cleanup command fails.
            failures = []
            commands = [
                (
                    "cmd",
                    "connectivity",
                    "airplane-mode",
                    "enable" if settings["airplane_mode_on"] == "1" else "disable",
                ),
                ("svc", "wifi", "enable" if settings["wifi_on"] == "1" else "disable"),
                ("svc", "data", "enable" if settings["mobile_data"] == "1" else "disable"),
            ]
            for command in commands:
                try:
                    self.run("shell", *command)
                except (RuntimeError, subprocess.TimeoutExpired) as error:
                    failures.append(str(error))
            if failures:
                raise RuntimeError("Could not restore emulator network settings: " + "; ".join(failures))

    def screenshot(self, path):
        result = subprocess.run(self.adb + ["exec-out", "screencap", "-p"], capture_output=True, timeout=30, check=True)
        path.write_bytes(result.stdout)
