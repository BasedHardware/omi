"""Fake Play edit lifecycle tests; no network or credentials."""

import copy
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

SCRIPTS = Path(__file__).resolve().parents[3] / "app" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import mobile_rollout_brake as brake

FIX = "Fixed pendant audio loss when the device reconnects."


class Request:
    def __init__(self, fn):
        self.fn = fn
        self.uri = "https://androidpublisher.googleapis.com/commit?alt=json"

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
        self.fraction_mismatch = False
        self.cleanup_error = False
        self.commit_request = None
        self.sources = {
            "internal": {
                "track": "internal",
                "releases": [{"versionCodes": ["1477"], "status": "completed", "name": "1.0.569"}],
            },
            "alpha": {"track": "alpha", "releases": []},
        }

    def edits(self):
        return self

    def tracks(self):
        return self

    def get(self, **kw):
        self.calls.append(("get", kw))
        source = self.live if kw["track"] == "production" else self.sources[kw["track"]]
        return Request(lambda: copy.deepcopy(source))

    def update(self, **kw):
        self.calls.append(("update", kw))
        self.pending = copy.deepcopy(kw["body"])

        def response():
            if self.update_mismatch:
                return {}
            body = copy.deepcopy(self.pending)
            if self.fraction_mismatch:
                body["releases"][1]["userFraction"] = 0.5
            return body

        return Request(response)

    def commit(self, **kw):
        self.calls.append(("commit", kw))

        def execute():
            if not self.mismatch:
                self.live = self.pending
            return {}

        self.commit_request = Request(execute)
        return self.commit_request

    def insert(self, **kw):
        self.calls.append(("insert", kw))
        return Request(lambda: {"id": "readback"})

    def delete(self, **kw):
        self.calls.append(("delete", kw))
        if self.cleanup_error:
            raise RuntimeError("simulated cleanup failure")
        return Request(lambda: {})


class BrakeTests(unittest.TestCase):
    def run_action(self, play, action="halt", code="1471", confirm="brake"):
        return brake.run_brake(
            action, code, confirm, edit_factory=lambda: (play, "original"), quiescence_check=lambda: None
        )

    def test_halt_preserves_everything_except_status_and_reads_fresh_edit(self):
        play = FakePlay()
        expected = copy.deepcopy(play.live)
        expected["releases"][1]["status"] = "halted"
        # Held-changes mode path (constant True): the module default is False
        # since 2026-10-27, so the held commit parameter is patched in.
        with patch.object(brake.promote, "CHANGES_NOT_SENT_FOR_REVIEW", True):
            self.assertEqual(
                self.run_action(play),
                "BRAKE_RESULT action=halt versionCode=1471 status_before=inProgress status_after=halted userFraction=0.1",
            )
        self.assertEqual(play.live, expected)
        self.assertEqual([name for name, _ in play.calls], ["get", "update", "commit", "insert", "get", "delete"])
        self.assertEqual(play.calls[-2][1]["editId"], "readback")
        self.assertEqual(
            parse_qs(urlsplit(play.commit_request.uri).query)["changesInReviewBehavior"], ["ERROR_IF_IN_REVIEW"]
        )
        self.assertEqual(parse_qs(urlsplit(play.commit_request.uri).query)["changesNotSentForReview"], ["true"])
        for _, args in play.calls:
            self.assertEqual(args["packageName"], "com.friend.ios")
            if "track" in args:
                self.assertEqual(args["track"], "production")

    def test_held_mode_follows_the_shared_constant(self):
        # With the constant False (the module default since 2026-10-27, when
        # Play went back to auto-sending changes for review), a brake commit
        # must not hold its changes: only the in-review guard stays.
        play = FakePlay()
        with patch.object(brake.promote, "CHANGES_NOT_SENT_FOR_REVIEW", False):
            self.assertIn("status_after=halted", self.run_action(play))
        query = parse_qs(urlsplit(play.commit_request.uri).query)
        self.assertEqual(query["changesInReviewBehavior"], ["ERROR_IF_IN_REVIEW"])
        self.assertNotIn("changesNotSentForReview", query)

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

    def test_fraction_changed_by_update_response_never_commits(self):
        play = FakePlay()
        play.fraction_mismatch = True
        with self.assertRaises(brake.BrakeError):
            self.run_action(play)
        self.assertNotIn("commit", [name for name, _ in play.calls])

    def test_cleanup_failure_preserves_verified_result_and_original_error(self):
        play = FakePlay()
        play.cleanup_error = True
        self.assertIn("status_after=halted", self.run_action(play))
        with self.assertRaisesRegex(brake.BrakeError, "requires status=inProgress"):
            self.run_action(play)

    def test_country_targeted_mutation_refuses_without_stripping_fields(self):
        play = FakePlay()
        play.live["releases"][1]["countryTargeting"] = {"countries": ["US"]}
        before = copy.deepcopy(play.live)
        with self.assertRaisesRegex(brake.BrakeError, "country-targeted"):
            self.run_action(play)
        self.assertEqual(play.live, before)
        self.assertEqual([name for name, _ in play.calls], ["get", "delete"])

    def halted_play(self):
        play = FakePlay("halted")
        play.live["releases"][1]["releaseNotes"] = [
            {"language": "en-US", "text": "- Faster sync.\n- Longer battery.\n"},
            {"language": "de-DE", "text": "Schneller."},
            {"language": "fr-FR", "text": "- Faster sync.\n- Longer battery.\n"},
        ]
        return play

    def stage(self, play, code="1477", fraction="0.01", supersedes="1471", confirm="brake"):
        return brake.run_brake(
            "stage",
            code,
            confirm,
            user_fraction=fraction,
            supersedes=supersedes,
            notes_line=f"  {FIX}  ",
            edit_factory=lambda: (play, "original"),
            quiescence_check=lambda: None,
        )

    def test_stage_replaces_only_halted_release_at_requested_fraction(self):
        play = self.halted_play()
        completed = copy.deepcopy(play.live["releases"][0])
        # Held-changes mode path (constant True): the module default is False
        # since 2026-10-27, so the held commit parameter is patched in.
        with patch.object(brake.promote, "CHANGES_NOT_SENT_FOR_REVIEW", True):
            result = self.stage(play)
        self.assertTrue(result.startswith("BRAKE_RESULT action=stage versionCode=1477 status_before=absent"))
        self.assertIn("userFraction=0.01 supersedes=1471 superseded_status=halted superseded_userFraction=0.1", result)
        self.assertEqual(play.live["releases"][0], completed)
        staged = play.live["releases"][1]
        self.assertEqual(staged["versionCodes"], ["1477"])
        self.assertEqual(staged["status"], "inProgress")
        self.assertEqual(staged["userFraction"], 0.01)
        self.assertRegex(staged["name"], r"^1\.0\.569 \(gate \d{4}-\d{2}-\d{2}-\d{4}\)$")
        self.assertIsNotNone(brake.train._gate_receipt_dt(staged["name"]))
        self.assertEqual(
            staged["releaseNotes"],
            [
                {"language": "en-US", "text": f"- Faster sync.\n- Longer battery.\n{FIX}"},
                {"language": "de-DE", "text": "Schneller."},
                {"language": "fr-FR", "text": f"- Faster sync.\n- Longer battery.\n{FIX}"},
            ],
        )
        self.assertEqual(len(play.live["releases"]), 2)
        names = [name for name, _ in play.calls]
        self.assertEqual(names, ["get", "get", "get", "update", "commit", "insert", "get", "delete"])
        self.assertEqual(
            parse_qs(urlsplit(play.commit_request.uri).query)["changesInReviewBehavior"], ["ERROR_IF_IN_REVIEW"]
        )
        self.assertEqual(parse_qs(urlsplit(play.commit_request.uri).query)["changesNotSentForReview"], ["true"])
        self.assertEqual([args["track"] for name, args in play.calls if name == "update"], ["production"])

    def test_stage_refuses_unless_superseded_release_is_halted(self):
        for status in ["inProgress", "completed", "draft"]:
            play = self.halted_play()
            play.live["releases"][1]["status"] = status
            with self.assertRaisesRegex(brake.BrakeError, "halted"):
                self.stage(play)
            self.assertNotIn("update", [name for name, _ in play.calls])

    def test_stage_refuses_unexpected_production_or_source_state(self):
        cases = {
            "extra draft": lambda p: p.live["releases"].append(
                {"versionCodes": ["1480"], "status": "draft", "name": "1.0.570"}
            ),
            "already staged": lambda p: p.live["releases"][0].update(versionCodes=["1477"]),
            "missing source": lambda p: p.sources["internal"].update(releases=[]),
            "multi-code source": lambda p: p.sources["internal"]["releases"][0].update(versionCodes=["1477", "1478"]),
            "older source": lambda p: p.sources["internal"]["releases"][0].update(name="1.0.568"),
            "conflicting versions": lambda p: p.sources["alpha"].update(
                releases=[{"versionCodes": ["1477"], "status": "completed", "name": "1.0.570"}]
            ),
            "country targeted": lambda p: p.live["releases"][1].update(countryTargeting={"countries": ["US"]}),
            "no en-US notes": lambda p: p.live["releases"][1].update(releaseNotes=[{"language": "de-DE", "text": "x"}]),
            "notes too long": lambda p: p.live["releases"][1].update(
                releaseNotes=[{"language": "en-US", "text": "x" * 480}]
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                play = self.halted_play()
                mutate(play)
                with self.assertRaises((brake.BrakeError, brake.promote.PromotionError)):
                    self.stage(play)
                self.assertNotIn("update", [name for name, _ in play.calls])
                self.assertEqual(play.calls[-1][0], "delete")

    def test_stage_replaces_last_line_only_when_appending_passes_limit(self):
        play = self.halted_play()
        head = "- " + "a" * (brake.PLAY_NOTES_LIMIT - 60)
        long_text = f"{head}\n- Smaller fixes"
        for entry in play.live["releases"][1]["releaseNotes"]:
            if entry["language"] != "de-DE":
                entry["text"] = long_text
        self.stage(play)
        notes = {entry["language"]: entry["text"] for entry in play.live["releases"][1]["releaseNotes"]}
        self.assertEqual(notes["en-US"], f"{head}\n{FIX}")
        self.assertEqual(notes["fr-FR"], f"{head}\n{FIX}")
        self.assertEqual(notes["de-DE"], "Schneller.")

    def test_stage_keeps_semicolon_joined_android_notes_shape(self):
        play = self.halted_play()
        first = "a" * 320
        last = "b" * 150
        play.live["releases"][1]["releaseNotes"] = [{"language": "en-US", "text": f"{first}; {last}"}]
        brake.run_brake(
            "stage",
            "1477",
            "brake",
            user_fraction="0.01",
            supersedes="1471",
            notes_line="Fixes audio loss when your Omi reconnects",
            edit_factory=lambda: (play, "original"),
            quiescence_check=lambda: None,
        )
        self.assertEqual(
            play.live["releases"][1]["releaseNotes"],
            [{"language": "en-US", "text": f"{first}; Fixes audio loss when your Omi reconnects"}],
        )

    def test_stage_fraction_above_halted_fraction_refuses(self):
        play = self.halted_play()
        with self.assertRaisesRegex(brake.BrakeError, "must not exceed"):
            self.stage(play, fraction="0.2")
        self.assertNotIn("update", [name for name, _ in play.calls])

    def test_stage_bad_inputs_fail_before_authentication(self):
        for fraction, supersedes, confirm, line in [
            ("", "1471", "brake", FIX),
            ("0", "1471", "brake", FIX),
            ("1", "1471", "brake", FIX),
            ("nan", "1471", "brake", FIX),
            ("0.01", "", "brake", FIX),
            ("0.01", "1477", "brake", FIX),
            ("0.01", "1471", "", FIX),
            ("0.01", "1471", "brake", " "),
            ("0.01", "1471", "brake", "two\nlines"),
        ]:
            with self.subTest(fraction=fraction, supersedes=supersedes, confirm=confirm, line=line):
                with patch.object(brake.promote, "play_edit") as factory:
                    with self.assertRaises(brake.BrakeError):
                        brake.run_brake(
                            "stage", "1477", confirm, user_fraction=fraction, supersedes=supersedes, notes_line=line
                        )
                    factory.assert_not_called()

    def test_stage_update_or_readback_mismatch_fails_closed(self):
        play = self.halted_play()
        play.update_mismatch = True
        with self.assertRaises(brake.BrakeError):
            self.stage(play)
        self.assertNotIn("commit", [name for name, _ in play.calls])
        play = self.halted_play()
        play.mismatch = True
        with self.assertRaisesRegex(brake.BrakeError, "readback mismatch"):
            self.stage(play)

    def test_status_reads_staged_release_after_stage(self):
        play = self.halted_play()
        self.stage(play)
        self.assertEqual(
            self.run_action(play, "status", code="1477", confirm=""),
            "BRAKE_RESULT action=status versionCode=1477 status_before=inProgress status_after=inProgress userFraction=0.01",
        )

    def test_quiescence_checks_both_workflows_and_their_runs(self):
        paths = []

        def fetch(path):
            paths.append(path)
            return {"workflow_runs": [{"status": "completed"}]} if "/runs?" in path else {"state": "disabled_manually"}

        brake.require_quiesced_writers(fetch)
        self.assertEqual(len(paths), 4)
        for workflow in ["mobile_rollout_watch.yml", "mobile_daily_train.yml"]:
            self.assertIn(f"actions/workflows/{workflow}", paths)

    def test_active_unknown_or_unavailable_writers_refuse(self):
        for state in [{"state": "active"}, {}, {"state": "disabled_inactivity"}]:
            with self.assertRaises(brake.BrakeError):
                brake.require_quiesced_writers(lambda path: state)
        for runs in [None, [{"status": "in_progress"}], [{"status": "queued"}], [{}]]:
            with self.assertRaises(brake.BrakeError):
                brake.require_quiesced_writers(
                    lambda path: {"workflow_runs": runs} if "/runs?" in path else {"state": "disabled_manually"}
                )
        with self.assertRaises(brake.BrakeError):
            brake.require_quiesced_writers(lambda path: (_ for _ in ()).throw(OSError("offline")))

    def test_github_reads_use_token_only_when_present(self):
        seen = []

        class Response:
            def __enter__(self):
                return io.BytesIO(b"{}")

            def __exit__(self, *exc):
                return False

        def urlopen(request, timeout):
            seen.append(request.get_header("Authorization"))
            return Response()

        with patch.object(brake.urllib.request, "urlopen", urlopen):
            with patch.dict(brake.os.environ, {"GITHUB_TOKEN": "t0ken"}):
                brake.github_json("actions/workflows/x.yml")
            with patch.dict(brake.os.environ, {"GITHUB_TOKEN": ""}):
                brake.github_json("actions/workflows/x.yml")
        self.assertEqual(seen, ["Bearer t0ken", None])

    def test_unquiesced_writer_never_opens_edit(self):
        with patch.object(brake.promote, "play_edit") as factory:
            with self.assertRaises(brake.BrakeError):
                brake.run_brake(
                    "halt", "1471", "brake", quiescence_check=lambda: brake.require_quiesced_writers(lambda path: {})
                )
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
