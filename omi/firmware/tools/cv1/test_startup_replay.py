import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import startup_replay as replay

ROOT = Path(__file__).parent

class StartupReplayTests(unittest.TestCase):
    def setUp(self):
        self.first, self.provenance = replay.load_fixture(ROOT / "startup-fixtures", 0)
        self.repeat, _ = replay.load_fixture(ROOT / "startup-fixtures", 1)

    def descriptor(self, write=3, read=0, address=0x20002010, size=4096, flags=0):
        return b"SEGGER RTT\0".ljust(16, b"\0") + struct.pack("<8I", 3, 3, 0, address, size, write, read, flags)

    def test_actual_first_initialization(self):
        self.assertEqual(replay.observe(self.first)["state"], "initialization_reported")

    def test_actual_repeat_has_all_nine_same_milestones(self):
        compared = replay.compare_observations(replay.observe(self.first), replay.observe(self.repeat))
        self.assertEqual(len(compared), 9)
        self.assertTrue(all(row["first"] and row["repeat"] for row in compared.values()))

    def test_startup_self_reports_do_not_certify_peripherals(self):
        obs = replay.observe(self.first)
        for key in ("independent_ble_verified", "audio_health_verified", "storage_integrity_verified", "continuous_stability_verified"):
            self.assertFalse(obs[key])

    def test_utc_warnings_preserved_without_boot_failure(self):
        obs = replay.observe(self.repeat)
        self.assertEqual(len(obs["warnings"]), 2)
        self.assertFalse(obs["errors"])
        self.assertEqual(obs["state"], "initialization_reported")

    def test_explicit_error_not_hidden_by_success_line(self):
        obs = replay.observe(self.first + "\n<err> main: storage failed\n")
        self.assertEqual(obs["state"], "error_reported")
        self.assertEqual(len(obs["errors"]), 1)

    def test_missing_milestone_is_incomplete_not_failed_boot(self):
        text = self.first.split("Advertising successfully started")[0]
        self.assertEqual(replay.observe(text)["state"], "incomplete_observation")

    def test_actual_clipped_success_line_remains_observation(self):
        self.assertIn("Device initialized successfull", self.repeat)
        self.assertEqual(replay.observe(self.repeat)["state"], "initialization_reported")

    def test_empty_snapshot_never_implies_failed_boot(self):
        self.assertEqual(replay.observe("")["state"], "incomplete_observation")
        self.assertEqual(replay.decision_at([], 30, 30), "observation_timeout_unknown")

    def test_missing_initial_header_can_arrive_later(self):
        timeline = [{"host_seconds": 1.3, "valid_header": False}, {"host_seconds": 10.25, "valid_header": True, "text": self.repeat}]
        self.assertEqual(replay.decision_at(timeline, 2, 30), "waiting")
        self.assertEqual(replay.decision_at(timeline, 10.25, 30), "initialization_reported")

    def test_virtual_deadline_does_not_look_into_future(self):
        timeline = [{"host_seconds": 40, "valid_header": True, "text": self.repeat}]
        self.assertEqual(replay.decision_at(timeline, 30, 30), "observation_timeout_unknown")
        self.assertEqual(replay.decision_at(timeline, 40, 30), "initialization_reported")

    def test_policy_preserves_explicit_reported_error(self):
        rows = [{"host_seconds": 1, "valid_header": True, "text": "<err> main: init failed"}]
        self.assertEqual(replay.decision_at(rows, 2, 30), "error_reported")

    def test_uninitialized_control_block_is_unknown(self):
        with self.assertRaisesRegex(ValueError, "boot outcome unknown"):
            replay.decode_snapshot(bytes(48), bytes(4096))

    def test_wrong_pointer_and_blocking_mode_refused(self):
        for cb in (self.descriptor(address=0x20004000), self.descriptor(flags=2)):
            with self.assertRaises(ValueError): replay.decode_snapshot(cb, bytes(4096))

    def test_out_of_range_offsets_refused(self):
        for cb in (self.descriptor(write=4096), self.descriptor(read=4096)):
            with self.assertRaises(ValueError): replay.decode_snapshot(cb, bytes(4096))

    def test_wrapped_ring_bytes_reconstructed_without_writes(self):
        buf = bytearray(4096); buf[-2:] = b"ab"; buf[:2] = b"cd"
        value = replay.decode_snapshot(self.descriptor(write=2, read=4094), bytes(buf))
        self.assertEqual(value["raw"], b"abcd")
        self.assertEqual(value["target_writes"], 0)
        self.assertFalse(value["atomic_snapshot"])
        self.assertTrue(value["buffer_can_drop_later_output"])

    def test_non_utf8_capture_does_not_disappear(self):
        value = replay.decode_snapshot(self.descriptor(), b"a\xffb" + bytes(4093))
        self.assertEqual(value["raw"], b"a\xffb")
        self.assertEqual(value["observation"]["state"], "incomplete_observation")

    def test_actual_fixture_provenance_keeps_diagnostic_scope(self):
        self.assertEqual(self.provenance["variant"], "3.0.21-rttdiag2")
        self.assertIn("self-report", self.provenance["layer"])
        self.assertNotIn("CE:DC:D7", self.first)

    def test_tampered_fixture_refused(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(ROOT / "startup-fixtures", Path(d) / "fixtures")
            p = Path(d) / "fixtures/startup-1.log"; p.write_text(p.read_text() + "injected")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                replay.load_fixture(Path(d) / "fixtures", 0)

if __name__ == "__main__": unittest.main()
