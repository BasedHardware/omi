"""Offline contract tests: no Flutter subprocess, device, backend or credentials."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

import perf_device


class PerfDeviceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inventory = [
            {
                "id": "usb-fixture",
                "name": "Fixture phone",
                "targetPlatform": "ios",
                "emulator": False,
                "isSupported": True,
            }
        ]
        self.plan = perf_device.plan(self.inventory, "usb-fixture", self.root / "run")
        self.report = {
            "perf_device_smoke": {
                "schema": perf_device.SCHEMA,
                "scope": "standalone_shell_smoke",
                "build_mode": "profile",
                "run_id": self.plan["run_id"],
                "platform": "ios",
                "complete": True,
                "frame_count": 10,
                "build_us": [2000] * 10,
                "raster_us": [3000] * 10,
                "total_us": [6000] * 10,
            }
        }

    def test_exact_physical_id_and_explicit_profile_required(self):
        for changes in (
            {"emulator": True},
            {"emulator": None},
            {"isSupported": False},
            {"isConnected": False},
            {"targetPlatform": "darwin-arm64"},
            {"targetPlatform": None},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                perf_device.plan(
                    [{**self.inventory[0], **changes}], "usb-fixture", self.root / "run"
                )
        for inventory, device_id in (
            ([], "usb-fixture"),
            (self.inventory, "Fixture phone"),
            (self.inventory * 2, "usb-fixture"),
        ):
            with self.subTest(inventory=inventory), self.assertRaises(ValueError):
                perf_device.plan(inventory, device_id, self.root / "run")
        for changes in (
            {"mode": "debug"},
            {"mode": "release"},
            {"flavor": "prod"},
            {"profile": "mobile_beta"},
            {"target": "seeded"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                perf_device.plan(
                    self.inventory, "usb-fixture", self.root / "run", **changes
                )

    def test_command_is_dry_run_and_uses_existing_driver(self):
        self.assertIn("--profile", self.plan["command"])
        self.assertIn("--no-dds", self.plan["command"])
        self.assertIn("scripts/validate_mobile_build_config.sh", self.plan["command"])
        self.assertIn(
            "--driver=test_driver/integration_test_driver.dart", self.plan["command"]
        )
        self.assertIn(perf_device.TARGET, self.plan["command"])
        self.assertIn("PERF_DEVICE_RUN_ID=" + self.plan["run_id"], self.plan["command"])
        self.assertFalse((self.root / "run").exists())
        self.assertEqual(self.plan["approval"], "pending_specific_device_access")

    def test_existing_output_directory_rejected(self):
        (self.root / "run").mkdir()
        with self.assertRaisesRegex(ValueError, "stale"):
            perf_device.plan(self.inventory, "usb-fixture", self.root / "run")

    def test_android_physical_profile_accepted(self):
        inventory = [{**self.inventory[0], "targetPlatform": "android-arm64"}]
        result = perf_device.plan(inventory, "usb-fixture", self.root / "run")
        self.assertEqual(result["device"]["platform"], "android")

    def test_validated_artifact_still_makes_no_product_verdict(self):
        result = perf_device.collect(self.plan, self.report, 0)
        self.assertEqual(result["scope"], "standalone_shell_smoke")
        self.assertIn("no product-scenario performance verdict", result["claim"])

    def test_failure_stale_host_or_non_profile_response_rejected(self):
        for changes in (
            {"run_id": "previous-run"},
            {"platform": "android"},
            {"build_mode": "debug"},
            {"scope": "host_flutter_tester"},
            {"complete": False},
            {"complete": 1},
            {"frame_count": 0},
            {"frame_count": True},
            {"raster_us": [0] * 10},
            {"build_us": [float("nan")] * 10},
            {"build_us": [float("inf")] * 10},
            {"total_us": [-1] * 10},
            {"build_us": [2000]},
            {"total_us": [1000] * 10},
        ):
            report = copy.deepcopy(self.report)
            report["perf_device_smoke"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                perf_device.collect(self.plan, report, 0)
        for response, code in (
            (self.report, 1),
            ({"perf_scorecard": {}}, 0),
            (None, 0),
        ):
            with self.subTest(code=code), self.assertRaises(ValueError):
                perf_device.collect(self.plan, response, code)

    def test_cli_collects_only_matching_run_and_never_overwrites(self):
        inventory = self.root / "devices.json"
        inventory.write_text(json.dumps(self.inventory))
        plan_path = self.root / "plan.json"
        args = [
            "plan",
            "--inventory",
            str(inventory),
            "--device-id",
            "usb-fixture",
            "--output-dir",
            str(self.root / "run"),
            "--plan-file",
            str(plan_path),
        ]
        self.assertEqual(perf_device.main(args), 0)
        self.assertEqual(perf_device.main(args), 2)
        recorded = json.loads(plan_path.read_text())
        self.report["perf_device_smoke"]["run_id"] = recorded["run_id"]
        (self.root / "run").mkdir()
        (self.root / "run/integration_response_data.json").write_text(
            json.dumps(self.report)
        )
        collected = self.root / "collected.json"
        args = [
            "collect",
            "--plan-file",
            str(plan_path),
            "--drive-exit-code",
            "0",
            "--output",
            str(collected),
        ]
        self.assertEqual(perf_device.main(args), 0)
        self.assertEqual(perf_device.main(args), 2)
        self.assertEqual(len(json.loads(collected.read_text())["response_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
