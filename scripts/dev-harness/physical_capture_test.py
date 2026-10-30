"""Hermetic corruption tests for the offline recovery oracle."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from physical_capture_verify import EvidenceError, private_url, verify


class RecoveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        audio = b"synthetic-test-framed-audio"
        digest = hashlib.sha256(audio).hexdigest()
        (self.root / "app.ipa").write_bytes(b"test-build-not-a-device-artifact")
        row = {"device": "phone-mic", "timer_start": 100, "storage": "disk", "owner_uid": "omi-physical-fixture-test",
               "file_path": "audio.bin", "codec": "pcm16", "sample_rate": 16000, "channel": 1}
        for phase, status in [("before", "miss"), ("recovered", "miss"), ("uploaded", "uploaded"), ("completed", "synced")]:
            folder = self.root / phase
            folder.mkdir()
            (folder / "audio.bin").write_bytes(audio)
            self.write(f"{phase}/wals.json", {"wals": [{**row, "status": status, "job_id": "job-1" if phase in ("uploaded", "completed") else None}]})
        self.manifest = {"schema": "physical-capture-recovery-v1", "profile": "local_dev", "flavor": "dev",
                         "bundle_id": "com.omi.capture-qualification.test", "source_sha": "a" * 40,
                         "dirty_input_sha256": "b" * 64, "artifact": "app.ipa",
                         "artifact_sha256": hashlib.sha256((self.root / "app.ipa").read_bytes()).hexdigest(),
                         "api_base_url": "http://127.0.0.1:18765/", "auth_emulator_url": "http://127.0.0.1:19099/",
                         "synthetic_uid": "omi-physical-fixture-test", "wal_ids": ["phone-mic_100"],
                         "lifecycle": "lifecycle.json", "server_receipt": "server.json",
                         **{p: p for p in ("before", "recovered", "uploaded", "completed")}}
        self.lifecycle = {"bundle_id": self.manifest["bundle_id"], "before_process": "boot-1", "after_process": "boot-2", "observed_exit": True,
                          **dict(zip(("persisted_at_ms", "terminated_at_ms", "relaunched_at_ms", "recovered_at_ms", "uploaded_at_ms", "completed_at_ms"), range(1, 7)))}
        self.server = {"api_base_url": self.manifest["api_base_url"], "synthetic_uid": self.manifest["synthetic_uid"],
                       "status": "completed", "http_status": 202, "job_id": "job-1",
                       "files": [{"filename": "audio.bin", "bytes": len(audio), "sha256": digest}]}
        self.write("lifecycle.json", self.lifecycle)
        self.write("server.json", self.server)

    def write(self, path, value):
        (self.root / path).write_text(json.dumps(value))

    def run_oracle(self):
        self.write("manifest.json", self.manifest)
        return verify(self.root / "manifest.json")

    def test_consistent_artifacts_never_claim_hardware_qualification(self):
        result = self.run_oracle()
        self.assertEqual(result["status"], "artifact_consistency_passed")
        self.assertFalse(result["hardware_qualified"])

    def test_each_audio_snapshot_detects_corruption(self):
        for phase in ("before", "recovered", "uploaded", "completed"):
            with self.subTest(phase=phase):
                file = self.root / phase / "audio.bin"
                old = file.read_bytes()
                file.write_bytes(b"changed")
                with self.assertRaises(EvidenceError): self.run_oracle()
                file.write_bytes(old)

    def test_202_cannot_masquerade_as_completed(self):
        self.server["status"] = "queued"
        self.write("server.json", self.server)
        with self.assertRaises(EvidenceError): self.run_oracle()

    def test_process_reuse_and_unobserved_exit_refuse(self):
        for delta in ({"after_process": "boot-1"}, {"observed_exit": False}, {"recovered_at_ms": 1}):
            with self.subTest(delta=delta):
                self.write("lifecycle.json", {**self.lifecycle, **delta})
                with self.assertRaises(EvidenceError): self.run_oracle()

    def test_foreign_owner_and_missing_wal_refuse(self):
        source = json.loads((self.root / "recovered/wals.json").read_text())
        wrong = copy.deepcopy(source)
        wrong["wals"][0]["owner_uid"] = "someone-else"
        for value in (wrong, {"wals": []}):
            self.write("recovered/wals.json", value)
            with self.assertRaises(EvidenceError): self.run_oracle()

    def test_stale_build_and_public_endpoints_refuse(self):
        for endpoint in ("https://example.com/", "http://100.128.0.1:80/", "http://127.0.0.1:80/?token=x"):
            with self.assertRaises(EvidenceError): private_url(endpoint)
        (self.root / "app.ipa").write_bytes(b"rebuilt")
        with self.assertRaises(EvidenceError): self.run_oracle()

    def test_multiple_recordings_keep_independent_server_jobs(self):
        self.manifest["wal_ids"].append("phone-mic_101")
        for phase in ("before", "recovered", "uploaded", "completed"):
            path = f"{phase}/wals.json"
            source = json.loads((self.root / path).read_text())
            second = {**source["wals"][0], "timer_start": 101, "file_path": "second.bin"}
            if phase in ("uploaded", "completed"): second["job_id"] = "job-2"
            source["wals"].append(second)
            self.write(path, source)
            (self.root / phase / "second.bin").write_bytes((self.root / phase / "audio.bin").read_bytes())
        self.server.pop("job_id")
        self.server["files"][0]["job_id"] = "job-1"
        self.server["files"].append({**self.server["files"][0], "filename": "second.bin", "job_id": "job-2"})
        self.write("server.json", self.server)
        self.assertEqual(self.run_oracle()["recordings"], 2)
        self.server["files"][1]["job_id"] = "job-1"
        self.write("server.json", self.server)
        with self.assertRaises(EvidenceError): self.run_oracle()


if __name__ == "__main__":
    unittest.main()
