"""Fake Play edit lifecycle tests; no network or credentials."""

import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[3] / "app" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import mobile_rollout_brake as brake


class Request:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakePlay:
    def __init__(self, status="inProgress"):
        self.live = {
            "track": "production",
            "releases": [
                {"versionCodes": ["1460"], "status": "completed", "name": "old"},
                {"versionCodes": ["1471"], "status": status, "userFraction": 0.1, "name": "1.0.568"},
            ],
        }
        self.calls = []
        self.pending = None
        self.mismatch = False
        self.update_mismatch = False

    def edits(self):
        return self

    def tracks(self):
        return self

    def get(self, **kw):
        self.calls.append(("get", kw))
        return Request(lambda: copy.deepcopy(self.live))

    def update(self, **kw):
        self.calls.append(("update", kw))
        self.pending = copy.deepcopy(kw["body"])
        return Request(lambda: {} if self.update_mismatch else copy.deepcopy(self.pending))

    def commit(self, **kw):
        self.calls.append(("commit", kw))

        def execute():
            if not self.mismatch:
                self.live = self.pending
            return {}

        return Request(execute)

    def insert(self, **kw):
        self.calls.append(("insert", kw))
        return Request(lambda: {"id": "readback"})

    def delete(self, **kw):
        self.calls.append(("delete", kw))
        return Request(lambda: {})


class BrakeTests(unittest.TestCase):
    def run_action(self, play, action="halt", code="1471", confirm="brake"):
        return brake.run_brake(action, code, confirm, edit_factory=lambda: (play, "original"))

    def test_halt_preserves_everything_except_status_and_reads_fresh_edit(self):
        play = FakePlay()
        expected = copy.deepcopy(play.live)
        expected["releases"][1]["status"] = "halted"
        self.assertEqual(
            self.run_action(play),
            "BRAKE_RESULT action=halt versionCode=1471 status_before=inProgress status_after=halted userFraction=0.1",
        )
        self.assertEqual(play.live, expected)
        self.assertEqual([name for name, _ in play.calls], ["get", "update", "commit", "insert", "get", "delete"])
        self.assertEqual(play.calls[-2][1]["editId"], "readback")
        for _, args in play.calls:
            self.assertEqual(args["packageName"], "com.friend.ios")
            if "track" in args:
                self.assertEqual(args["track"], "production")

    def test_status_never_updates_or_commits(self):
        play = FakePlay()
        self.assertIn("status_after=inProgress", self.run_action(play, "status", confirm=""))
        self.assertEqual([name for name, _ in play.calls], ["get", "delete"])

    def test_resume_preserves_fraction(self):
        play = FakePlay("halted")
        self.assertIn("status_after=inProgress", self.run_action(play, "resume"))
        self.assertEqual(play.live["releases"][1]["userFraction"], 0.1)

    def test_bad_inputs_fail_before_authentication(self):
        for action, code, confirm in [("", "1471", "brake"), ("halt", "0", "brake"), ("halt", "1471", "")]:
            with self.subTest(action=action, code=code, confirm=confirm):
                with patch.object(brake.promote, "play_edit") as factory:
                    with self.assertRaises(brake.BrakeError):
                        brake.run_brake(action, code, confirm)
                    factory.assert_not_called()

    def test_wrong_status_or_missing_or_duplicate_code_refuses_mutation(self):
        for status in ["halted", "completed", "draft"]:
            play = FakePlay(status)
            with self.assertRaises(brake.BrakeError):
                self.run_action(play)
            self.assertEqual([name for name, _ in play.calls], ["get", "delete"])
        for code in ["9999", "1471"]:
            play = FakePlay()
            if code == "1471":
                play.live["releases"].append(copy.deepcopy(play.live["releases"][1]))
            with self.assertRaises(brake.BrakeError):
                self.run_action(play, code=code)

    def test_bad_fraction_refuses_mutation(self):
        for fraction in [None, True, 0, 1, float("nan"), "0.1"]:
            play = FakePlay()
            play.live["releases"][1]["userFraction"] = fraction
            with self.assertRaises(brake.BrakeError):
                self.run_action(play)
            self.assertNotIn("update", [name for name, _ in play.calls])

    def test_update_mismatch_never_commits(self):
        play = FakePlay()
        play.update_mismatch = True
        with self.assertRaises(brake.BrakeError):
            self.run_action(play)
        self.assertNotIn("commit", [name for name, _ in play.calls])

    def test_postcommit_mismatch_fails_closed(self):
        play = FakePlay()
        play.mismatch = True
        with self.assertRaises(brake.BrakeError):
            self.run_action(play)
        self.assertEqual(play.calls[-1][1]["editId"], "readback")


if __name__ == "__main__":
    unittest.main()
