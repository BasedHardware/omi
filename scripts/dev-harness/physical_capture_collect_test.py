"""Hermetic host lifecycle tests: no real device commands or external network."""

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from physical_capture_collect import Collector, Device
from physical_capture_verify import EvidenceError


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server = self.root / "server"
        self.server.mkdir()
        self.bundle = "com.omi.capture-qualification.test"
        self.uid = "omi-physical-fixture-test"
        self.api = "http://127.0.0.1:18765/"
        self.run = {
            "run_id": "run-test",
            "fixture_uid": self.uid,
            "api_base_url": self.api,
            "auth_emulator_url": "http://127.0.0.1:19099/",
        }
        self.write(self.server / "run.json", self.run)
        plist = {
            "CFBundleIdentifier": self.bundle,
            "CFBundleExecutable": "OmiCaptureQA",
            "CFBundleVersion": "1",
            "CFBundleShortVersionString": "1.0",
        }
        entries = {
            "Info.plist": plistlib.dumps(plist),
            "OmiCaptureQA": b"synthetic app executable",
        }
        artifact = self.root / "app.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            for name, data in entries.items():
                archive.writestr("OmiCaptureQA.app/" + name, data)
        receipt = {
            "built": True,
            "bundle_id": self.bundle,
            "git_head": "a" * 40,
            "dart_input_sha256": {"lib/main.dart": "b" * 64},
            "signed_app_file_sha256": {
                k: hashlib.sha256(v).hexdigest() for k, v in entries.items()
            },
            "defines": {
                "OMI_APP_PROFILE": "local_dev",
                "OMI_PHYSICAL_QUALIFICATION": "true",
                "OMI_PHYSICAL_FIXTURE_UID": self.uid,
                "OMI_API_BASE_URL": self.api,
                "OMI_FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1",
                "OMI_FIREBASE_AUTH_EMULATOR_PORT": "19099",
            },
        }
        self.write(self.root / "build.json", receipt)
        self.args = argparse.Namespace(
            device="00000000-0000000000000001",
            bundle_id=self.bundle,
            artifact=artifact,
            build_receipt=self.root / "build.json",
            server_receipts=self.server,
            output=self.root / "evidence",
            timeout=30,
        )
        self.raw = b"actual synthetic framed WAL"
        self.job = "fixture-" + "1" * 32
        self.boot = "123_1000"
        self.after = "456_2000"
        self.phase = "before"
        self.calls = []
        self.wrong_process = False
        self.corrupt = False
        self.exit_visible = True
        self.running = True
        self.launched = False
        self.sent_upload = False
        self.appurl = "file:///private/var/containers/Bundle/Application/AAAAAAAA-BBBB/OmiCaptureQA.app/"
        self.emit("boot", {"source": "phone_mic"})
        self.emit("awaiting_termination", {"files": [self.file("miss", None)]})
        self.real_sleep = time.sleep

    def write(self, path, value):
        path.write_text(json.dumps(value))

    def file(self, status, job):
        return {
            "wal_id": "phone-mic_100",
            "filename": "audio.bin",
            "bytes": len(self.raw),
            "sha256": hashlib.sha256(self.raw).hexdigest(),
            "status": status,
            "job_id": job,
        }

    def emit(self, phase, extra=None):
        self.write(
            self.server / ("event-" + phase + ".json"),
            {
                "phase": phase,
                "run_id": "run-test",
                "fixture_uid": self.uid,
                "process": self.after if self.launched else self.boot,
                **(extra or {}),
            },
        )

    def progress(self, *args):
        if (
            self.server / "host-upload-approved.json"
        ).exists() and not self.sent_upload:
            self.sent_upload = True
            self.emit("uploaded", {"files": [self.file("uploaded", self.job)]})
            self.emit("completed", {"files": [self.file("synced", self.job)]})
            self.write(
                self.server / ("completed-" + self.job + ".json"),
                {
                    "run_id": "run-test",
                    "job_id": self.job,
                    "status": "completed",
                    "http_status": 202,
                    "files": [
                        {
                            "filename": "audio.bin",
                            "bytes": len(self.raw),
                            "sha256": hashlib.sha256(self.raw).hexdigest(),
                            "job_id": self.job,
                        }
                    ],
                },
            )

    def call(self, args):
        self.calls.append(args)
        self.real_sleep(0.002)
        if args[:2] == ["copy", "from"]:
            source = args[args.index("--source") + 1]
            destination = Path(args[args.index("--destination") + 1])
            if source.endswith("physical_capture_state.json"):
                self.write(
                    destination,
                    {
                        "process": self.boot,
                        "wal_ids": ["phone-mic_100"],
                        "source": "phone_mic",
                        "fixture_uid": self.uid,
                    },
                )
            elif source.endswith("wals.json"):
                phase = source.split("/")[-2]
                status = {
                    "before": "miss",
                    "recovered": "miss",
                    "uploaded": "uploaded",
                    "completed": "synced",
                }[phase]
                self.write(
                    destination,
                    {
                        "wals": [
                            {
                                "device": "phone-mic",
                                "timer_start": 100,
                                "storage": "disk",
                                "owner_uid": self.uid,
                                "file_path": "audio.bin",
                                "codec": "pcm16",
                                "sample_rate": 16000,
                                "channel": 1,
                                "status": status,
                                "job_id": (
                                    self.job
                                    if phase in ("uploaded", "completed")
                                    else None
                                ),
                            }
                        ]
                    },
                )
            else:
                destination.write_bytes(
                    b"corrupted"
                    if self.corrupt and "/recovered/" in source
                    else self.raw
                )
            return {}
        if args[:2] == ["info", "apps"]:
            return {
                "apps": [
                    {
                        "bundleIdentifier": self.bundle,
                        "url": self.appurl,
                        "version": "1.0",
                        "bundleVersion": "1",
                    }
                ]
            }
        if args[:2] == ["info", "processes"]:
            if not self.running:
                return {"runningProcesses": []}
            return {
                "runningProcesses": [
                    {
                        "processIdentifier": 456 if self.launched else 123,
                        "executable": self.appurl
                        + ("Other" if self.wrong_process else "OmiCaptureQA"),
                    }
                ]
            }
        if args[:2] == ["process", "terminate"]:
            self.assertEqual(args, ["process", "terminate", "--pid", "123", "--kill"])
            self.running = not self.exit_visible
            return {}
        if args[:2] == ["process", "launch"]:
            self.assertFalse(self.running)
            self.assertEqual(args[2], self.bundle)
            self.running = True
            self.launched = True
            self.emit("recovered", {"files": [self.file("miss", None)]})
            return {}
        raise AssertionError("unexpected device command")

    def collect(self):
        with patch(
            "physical_capture_collect.subprocess.run",
            side_effect=AssertionError("real subprocess forbidden"),
        ), patch("physical_capture_collect.time.sleep", side_effect=self.progress):
            return Collector(self.args, device=self).execute()

    def test_complete_sequence_runs_offline_oracle(self):
        result = self.collect()
        self.assertEqual(result["status"], "artifact_consistency_passed")
        self.assertFalse(result["hardware_qualified"])
        self.assertTrue(self.sent_upload)
        self.assertTrue((self.args.output / "manifest.json").exists())
        self.assertEqual(
            json.loads((self.server / "host-upload-approved.json").read_text())[
                "run_id"
            ],
            "run-test",
        )

    def test_foreign_process_is_never_killed(self):
        self.wrong_process = True
        with self.assertRaises(EvidenceError):
            self.collect()
        self.assertFalse(any(c[:2] == ["process", "terminate"] for c in self.calls))

    def test_corrupted_recovery_never_approves_upload(self):
        self.corrupt = True
        with self.assertRaises(EvidenceError):
            self.collect()
        self.assertFalse((self.server / "host-upload-approved.json").exists())

    def test_stale_approval_refused_before_device(self):
        self.write(self.server / "host-upload-approved.json", {"command": "upload"})
        with self.assertRaises(EvidenceError):
            self.collect()
        self.assertEqual(self.calls, [])

    def test_endpoint_mismatch_refused_before_device(self):
        self.write(
            self.server / "run.json",
            {**self.run, "api_base_url": "http://127.0.0.1:18766/"},
        )
        with self.assertRaises(EvidenceError):
            self.collect()
        self.assertEqual(self.calls, [])

    def test_run_restart_refused_before_kill(self):
        collector = Collector(self.args, device=self)
        self.write(self.server / "run.json", {**self.run, "run_id": "new-run"})
        with self.assertRaises(EvidenceError):
            collector.execute()
        self.assertFalse(any(c[:2] == ["process", "terminate"] for c in self.calls))

    def test_artifact_replaced_after_construction_refuses_before_device(self):
        collector = Collector(self.args, device=self)
        with zipfile.ZipFile(self.args.artifact, "a") as archive:
            archive.writestr("OmiCaptureQA.app/foreign", b"replacement")
        with self.assertRaises(EvidenceError):
            collector.execute()
        self.assertEqual(self.calls, [])

    def test_receipt_replaced_after_construction_refuses_before_device(self):
        collector = Collector(self.args, device=self)
        data = json.loads(self.args.build_receipt.read_text())
        data["git_head"] = "b" * 40
        self.write(self.args.build_receipt, data)
        with self.assertRaises(EvidenceError):
            collector.execute()
        self.assertEqual(self.calls, [])

    def test_stale_run_event_never_admitted(self):
        collector = Collector(self.args, device=self)
        collector.output.mkdir()
        stale = self.server / "event-awaiting_termination.json"
        row = json.loads(stale.read_text())
        row["run_id"] = "old-run"
        self.write(stale, row)

        # Force a finite deadline after the first poll instead of waiting on hardware.
        def expire(_):
            collector.deadline = 0

        with patch("physical_capture_collect.time.sleep", side_effect=expire):
            with self.assertRaises(EvidenceError):
                collector.event("awaiting_termination")
        self.assertFalse(
            (collector.output / "event-awaiting_termination.json").exists()
        )

    def test_unobserved_exit_never_relaunches(self):
        self.exit_visible = False
        collector = Collector(self.args, device=self)

        def expire(_):
            collector.deadline = 0

        with patch("physical_capture_collect.time.sleep", side_effect=expire):
            with self.assertRaises(EvidenceError):
                collector.execute()
        self.assertFalse(any(c[:2] == ["process", "launch"] for c in self.calls))
        self.assertFalse((self.server / "host-upload-approved.json").exists())

    def test_production_bundle_refused(self):
        self.args.bundle_id = "com.friend.ios"
        with self.assertRaises(EvidenceError):
            self.collect()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
