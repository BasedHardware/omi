#!/usr/bin/env python3
"""Offline behavioral failures for the emulator acceptance boundary."""

from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from android_emulator import Emulator
from android_startup_smoke import apk_identity, assert_healthy, run_smoke, screen_from_instrumentation


class StartupTests(unittest.TestCase):
    def test_survival_is_not_enough_without_rendered_first_run_screen(self):
        for ui in ("", "Startup failed", "Recovering Omi", "Splash screen"):
            with self.subTest(ui=ui), self.assertRaisesRegex(ValueError, "render"):
                assert_healthy("", "com.friend.ios.dev", "12", "12", "boot", "boot", ui)
        assert_healthy("", "com.friend.ios.dev", "12", "12", "boot", "boot", "Get Started")

    def test_native_fatal_dart_fatal_anr_or_restart_fail(self):
        for log in (
            "FATAL EXCEPTION: main\nProcess: com.friend.ios.dev, PID: 12",
            "ANR in com.friend.ios.dev",
            "Unhandled Exception: boot failed",
        ):
            with self.subTest(log=log), self.assertRaisesRegex(ValueError, "exception|ANR"):
                assert_healthy(log, "com.friend.ios.dev", "12", "12", "boot", "boot", "Get Started")
        for pid, current_pid, boot in (("", "", "boot"), ("12", "13", "boot"), ("12", "12", "new-boot")):
            with self.subTest(pid=pid), self.assertRaises(ValueError):
                assert_healthy("", "com.friend.ios.dev", pid, current_pid, "boot", boot, "Get Started")

    def test_multiline_accessibility_capture_and_failed_or_wrong_app_probe(self):
        xml = '<screen package="com.friend.ios.dev"><node description="multi\nline"/><node description="Get Started"/></screen>'
        dump = "INSTRUMENTATION_RESULT: screen=" + xml + "\nINSTRUMENTATION_CODE: -1"
        self.assertEqual(screen_from_instrumentation(dump, "com.friend.ios.dev"), xml)
        for invalid in (
            dump.replace("CODE: -1", "CODE: 0"),
            "INSTRUMENTATION_FAILED: missing probe",
            dump.replace("com.friend.ios.dev", "other.app"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                screen_from_instrumentation(invalid, "com.friend.ios.dev")

    def test_identity_comes_from_artifact_and_rejects_other_apps(self):
        with patch("android_startup_smoke.subprocess.run") as run:
            run.return_value.stdout = "package: name='com.friend.ios' versionCode='1338' versionName='1.0.554'\n"
            self.assertEqual(apk_identity(Path("bundle.apk"), Path("aapt"))["version_code"], "1338")
            run.return_value.stdout = "package: name='another.app' versionCode='1' versionName='1'\n"
            with self.assertRaises(ValueError):
                apk_identity(Path("bundle.apk"), Path("aapt"))

    def test_existing_install_is_refused_before_clear_install_or_network_changes(self):
        device = Mock()
        device.run.return_value = "package:com.friend.ios.dev"
        with tempfile.TemporaryDirectory() as directory, patch(
            "android_startup_smoke.apk_identity", return_value={"package": "com.friend.ios.dev"}
        ):
            with self.assertRaisesRegex(ValueError, "fresh emulator"):
                run_smoke(device, Path("app.apk"), Path(directory), aapt=Path("aapt"))
        device.offline.assert_not_called()
        self.assertEqual(device.run.call_args.args, ("shell", "pm", "list", "packages", "com.friend.ios"))

    def test_full_runner_saves_success_or_failure_receipt_and_uninstalls_owned_apk(self):
        for fatal in (False, True):
            with self.subTest(fatal=fatal), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                apk = root / "app.apk"
                apk.write_bytes(b"fixture artifact")
                device = Mock(serial="emulator-5554")
                device.require_isolated.return_value = "boot"
                device.offline.return_value = nullcontext()
                commands = []

                def adb(*command):
                    commands.append(command)
                    if command == ("shell", "getprop", "ro.build.version.sdk"):
                        return "36"
                    if command[:4] == ("shell", "am", "start", "-W"):
                        return "Status: ok"
                    if command[:2] == ("shell", "pidof com.friend.ios.dev || true"):
                        return "12"
                    if command == ("shell", "cat", "/proc/sys/kernel/random/boot_id"):
                        return "boot"
                    if command == ("shell", "pm", "path", "com.omi.fgsprobe"):
                        return "package:/data/app/probe.apk"
                    if command[:4] == ("shell", "am", "instrument", "-w"):
                        return 'INSTRUMENTATION_RESULT: screen=<screen package="com.friend.ios.dev">Get Started</screen>\nINSTRUMENTATION_CODE: -1'
                    if command[0] == "logcat" and "-d" in command:
                        return "Process: com.friend.ios.dev, PID: 12" if fatal else ""
                    return ""

                device.run.side_effect = adb
                identity = {"package": "com.friend.ios.dev", "version_code": "992", "version_name": "1"}
                with patch("android_startup_smoke.apk_identity", return_value=identity), patch(
                    "android_startup_smoke.time.monotonic", side_effect=[0, 1, 21, 22]
                ):
                    if fatal:
                        with self.assertRaisesRegex(ValueError, "exception"):
                            run_smoke(device, apk, root / "output", aapt=Path("aapt"), rounds=1)
                    else:
                        run_smoke(device, apk, root / "output", aapt=Path("aapt"), rounds=1)
                receipt = json.loads((root / "output/receipt.json").read_text())
                self.assertEqual(receipt["passed"], not fatal)
                self.assertEqual(commands[-1], ("uninstall", "com.friend.ios.dev"))
                self.assertTrue((root / "output/0-startup.log").exists())
                self.assertEqual(len(receipt["launches"]), 0 if fatal else 1)

    def test_physical_device_is_refused(self):
        device = Emulator("physical-device")
        with patch.object(device, "run") as adb, self.assertRaisesRegex(ValueError, "physical"):
            device.require_isolated()
        adb.assert_not_called()

    def test_network_isolation_failure_restores_original_settings(self):
        device = Emulator("emulator-5554")
        commands = []

        def adb(*command):
            commands.append(command)
            if command[:4] == ("shell", "settings", "get", "global"):
                return "0" if command[-1] == "airplane_mode_on" else "1"
            if command == ("shell", "dumpsys", "connectivity"):
                return "Active default network: 100"
            return ""

        with patch.object(device, "require_isolated"), patch.object(device, "run", side_effect=adb), patch(
            "android_emulator.time.monotonic", side_effect=[0, 11]
        ):
            with self.assertRaisesRegex(ValueError, "refusing"):
                with device.offline():
                    self.fail("Online emulator must never reach app execution")
        self.assertEqual(
            commands[-3:],
            [
                ("shell", "cmd", "connectivity", "airplane-mode", "disable"),
                ("shell", "svc", "wifi", "enable"),
                ("shell", "svc", "data", "enable"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
