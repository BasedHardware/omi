#!/usr/bin/env python3
"""Offline behavioral contract for the foreground-service probe runner."""

import itertools
from pathlib import Path
import tempfile
import unittest

from android_fgs_probe import ACTION_VERIFIED, ACTIVE_MODES, PACKAGE, run_case

FOREGROUND_SERVICE = (
    "ACTIVITY MANAGER SERVICES (dumpsys activity services)\n"
    "  * ServiceRecord{1a2b3c u0 com.omi.fgsprobe/com.friend.ios.sync.SyncTransferForegroundService}\n"
    "    isForeground=true foregroundId=2003 foregroundNoti=Notification(...)\n"
)
NO_SERVICE = "ACTIVITY MANAGER SERVICES (dumpsys activity services)\n  (nothing)\n"
# dumpsys appends the global "Last ANR service" section even when invoked with
# a package filter; on a CI emulator that record can name a Google Play
# Services provider that ANR'd mid-run.
FOREIGN_LAST_ANR_SERVICE = (
    "  Last ANR service:\n"
    "ServiceRecord{ffdf3b4 u0 com.google.android.gms/com.google.android.location"
    ".internal.server.HardwareArProviderService c:android}\n"
)
PROBE_LAST_ANR_SERVICE = (
    "  Last ANR service:\n"
    "ServiceRecord{1a2b3c u0 com.omi.fgsprobe/com.friend.ios.sync"
    ".SyncTransferForegroundService c:android}\n"
)
WAKE_LOCK_HELD = (
    "Wake Locks: size=1\n"
    "  PARTIAL_WAKE_LOCK 'omi:sync-transfer' ACQ=-1s355ms (uid=10189 pid=4782 ws=null)\n"
    "Suspend Blockers: size=0\n"
)
WAKE_LOCK_FREE = "Wake Locks: size=0\nSuspend Blockers: size=0\n"


class FakeEmulator:
    """Scripted adb for one cold launch.

    The fake activity reports ACTIVE after ``polls_before_active`` logcat
    polls and, like the real probe activity, stops the service only once the
    runner broadcasts ACTION_VERIFIED. With ``fallback`` that stop is labelled
    with the activity's VERIFY_TIMEOUT marker instead of VERIFIED; the
    activity's own 30 s timer is not modelled. ``active`` controls whether the
    service is actually foreground with its wake lock when ACTIVE is reported.
    """

    def __init__(self, mode, *, active=True, polls_before_active=1, fallback=False):
        self.mode = mode
        self.active = active
        self.polls_before_active = polls_before_active
        self.fallback = fallback
        self.commands = []
        self.polls = 0
        # Modes without an ACTIVE phase tear the service down before SURVIVED.
        self.stopped = mode not in ACTIVE_MODES

    def __call__(self, *command):
        self.commands.append(command)
        if command == ("shell", "cat", "/proc/sys/kernel/random/boot_id"):
            return "boot"
        if command[:2] == ("logcat", "-d"):
            self.polls += 1
            lines = [f"BEGIN mode={self.mode}", "ACCEPTED", "Foreground promotion accepted"]
            if self.mode == "background-stop":
                lines.append("BACKGROUND_STOP")
            if self.mode in ACTIVE_MODES:
                if self.polls > self.polls_before_active:
                    lines.append(f"ACTIVE mode={self.mode}")
                if self.stopped:
                    lines.append(f"{'VERIFY_TIMEOUT' if self.fallback else 'VERIFIED'} mode={self.mode}")
                    lines.append(f"SURVIVED mode={self.mode}")
            else:
                lines.append(f"SURVIVED mode={self.mode}")
            return "\n".join(lines)
        if command[:3] == ("shell", "am", "broadcast"):
            self.stopped = True
            return "Broadcast completed: result=0"
        if command[:4] == ("shell", "dumpsys", "activity", "services"):
            return FOREGROUND_SERVICE if self.active and not self.stopped else NO_SERVICE
        if command[0] == "shell" and command[1].startswith("dumpsys power"):
            return WAKE_LOCK_HELD if self.active and not self.stopped else WAKE_LOCK_FREE
        return ""

    def indexes(self, *prefix):
        return [index for index, command in enumerate(self.commands) if command[: len(prefix)] == prefix]


def run(device, mode):
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        # A counting clock bounds the poll loop without wall time.
        result = run_case(device, mode, 0, output, "boot", clock=itertools.count().__next__, sleep=lambda _: None)
        return result, sorted(path.name for path in output.iterdir())


class ProbeRunnerTests(unittest.TestCase):
    def test_active_is_acknowledged_only_after_the_live_service_is_verified(self):
        for mode in ACTIVE_MODES:
            with self.subTest(mode=mode):
                device = FakeEmulator(mode, polls_before_active=3)
                result, files = run(device, mode)
                self.assertTrue(result["passed"])
                broadcasts = device.indexes("shell", "am", "broadcast")
                self.assertEqual(len(broadcasts), 1)
                self.assertIn("--receiver-foreground", device.commands[broadcasts[0]])
                self.assertIn(ACTION_VERIFIED, device.commands[broadcasts[0]])
                self.assertIn(PACKAGE, device.commands[broadcasts[0]])
                first_services = device.indexes("shell", "dumpsys", "activity", "services")[0]
                first_power = [i for i, c in enumerate(device.commands) if c[0] == "shell" and "dumpsys power" in c[1]][0]
                self.assertLess(first_services, broadcasts[0])
                self.assertLess(first_power, broadcasts[0])
                self.assertIn(f"0-{mode}-active-services.log", files)
                self.assertIn(f"0-{mode}-active-power.log", files)
                self.assertIn(f"0-{mode}-active.log", files)
                self.assertIn(f"0-{mode}-notifications.log", files)

    def test_verification_latency_cannot_race_the_stop(self):
        # The activity holds its stop until the broadcast, so however many polls
        # or snapshots the runner needs, it still observes the live service.
        device = FakeEmulator("burst", polls_before_active=40)
        result, _ = run(device, "burst")
        self.assertTrue(result["passed"])
        self.assertGreater(device.polls, 40)

    def test_inactive_service_at_active_saves_evidence_and_fails_without_acknowledging(self):
        device = FakeEmulator("burst", active=False)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(SystemExit, "not foreground with its wake lock.*0-burst-active-services.log"):
                run_case(device, "burst", 0, output, "boot", clock=itertools.count().__next__, sleep=lambda _: None)
            files = sorted(path.name for path in output.iterdir())
        self.assertEqual(files, ["0-burst-active-power.log", "0-burst-active-services.log", "0-burst-active.log"])
        self.assertEqual(device.indexes("shell", "am", "broadcast"), [])

    def test_runner_rejects_the_activity_fallback_marker(self):
        # Pins the runner's half only: the activity's 30 s timer that emits
        # VERIFY_TIMEOUT runs on the device and is not modelled here.
        device = FakeEmulator("restart", fallback=True)
        result, _ = run(device, "restart")
        self.assertFalse(result["passed"])

    def test_cleanup_scopes_leaked_service_records_to_the_probe_package(self):
        class NoisyServicesEmulator(FakeEmulator):
            def __call__(self, *command):
                if command[:4] == ("shell", "dumpsys", "activity", "services"):
                    return NO_SERVICE + anr_record
                return super().__call__(*command)

        for anr_record, expected in ((FOREIGN_LAST_ANR_SERVICE, True), (PROBE_LAST_ANR_SERVICE, False)):
            with self.subTest(probe_package_in_anr_record=not expected):
                result, _ = run(NoisyServicesEmulator("empty"), "empty")
                self.assertEqual(result["passed"], expected)

    def test_modes_without_an_active_phase_neither_verify_nor_acknowledge(self):
        for mode in ("empty", "orphan-stop", "background-stop"):
            with self.subTest(mode=mode):
                device = FakeEmulator(mode)
                result, files = run(device, mode)
                self.assertTrue(result["passed"])
                self.assertEqual(device.indexes("shell", "am", "broadcast"), [])
                self.assertEqual([name for name in files if "-active" in name], [])
                self.assertEqual(len(device.indexes("shell", "dumpsys", "activity", "services")), 1)


if __name__ == "__main__":
    unittest.main()
