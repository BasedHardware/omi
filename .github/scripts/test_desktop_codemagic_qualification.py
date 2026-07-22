#!/usr/bin/env python3
"""Behavioral tests for the Codemagic qualification lane driver."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import desktop_codemagic_qualification as lane


class VerifyResultPayloadTests(unittest.TestCase):
    TAG = "v0.12.111+12111-macos"
    SHA = "a" * 40

    def test_accepts_exact_binding(self) -> None:
        lane.verify_result_payload(
            {"ok": True, "release_tag": self.TAG, "source_sha": self.SHA}, self.TAG, self.SHA
        )

    def test_rejects_not_ok(self) -> None:
        with self.assertRaises(SystemExit):
            lane.verify_result_payload(
                {"ok": False, "release_tag": self.TAG, "source_sha": self.SHA}, self.TAG, self.SHA
            )

    def test_rejects_other_tag(self) -> None:
        with self.assertRaises(SystemExit):
            lane.verify_result_payload(
                {"ok": True, "release_tag": "v0.12.110+12110-macos", "source_sha": self.SHA},
                self.TAG,
                self.SHA,
            )

    def test_rejects_other_sha(self) -> None:
        with self.assertRaises(SystemExit):
            lane.verify_result_payload(
                {"ok": True, "release_tag": self.TAG, "source_sha": "b" * 40}, self.TAG, self.SHA
            )


class StartBuildTests(unittest.TestCase):
    def test_dispatch_binds_tag_and_short_lived_token(self) -> None:
        captured: dict = {}

        def fake_request(url, token, payload=None):
            captured["url"] = url
            captured["payload"] = payload
            return {"buildId": "abc123"}

        with mock.patch.object(lane, "_request", side_effect=fake_request):
            build_id = lane.start_build(
                "cm-token", "app", "omi-desktop-qualification", "main", "v0.12.111+12111-macos", "gh-tok"
            )
        self.assertEqual(build_id, "abc123")
        variables = captured["payload"]["environment"]["variables"]
        self.assertEqual(variables["OMI_QUALIFY_TAG"], "v0.12.111+12111-macos")
        self.assertEqual(variables["OMI_QUALIFY_GH_TOKEN"], "gh-tok")
        self.assertEqual(captured["payload"]["branch"], "main")

    def test_missing_build_id_fails(self) -> None:
        with mock.patch.object(lane, "_request", return_value={}):
            with self.assertRaises(SystemExit):
                lane.start_build("cm-token", "app", "wf", "main", "v0.12.111+12111-macos", "gh-tok")


class PollBuildTests(unittest.TestCase):
    def test_returns_on_terminal_failure_status(self) -> None:
        with mock.patch.object(lane, "get_build", return_value={"status": "failed"}):
            build = lane.poll_build("token", "build", poll_seconds=0, timeout_minutes=1)
        self.assertEqual(build["status"], "failed")

    def test_polls_through_transitional_statuses(self) -> None:
        statuses = iter(["queued", "building", "finishing", "finished"])
        with mock.patch.object(lane, "get_build", side_effect=lambda *_: {"status": next(statuses)}):
            with mock.patch.object(lane.time, "sleep"):
                build = lane.poll_build("token", "build", poll_seconds=1, timeout_minutes=1)
        self.assertEqual(build["status"], "finished")


class FetchResultArtifactTests(unittest.TestCase):
    def test_missing_artifact_fails(self) -> None:
        with self.assertRaises(SystemExit):
            lane.fetch_result_artifact("token", {"artefacts": [{"name": "other.json", "url": "x"}]})

    def test_downloads_named_artifact(self) -> None:
        payload = {"ok": True}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with mock.patch.object(lane.urllib.request, "urlopen", return_value=FakeResponse()):
            result = lane.fetch_result_artifact(
                "token",
                {"artefacts": [{"name": "qualification-result.json", "url": "https://example/x"}]},
            )
        self.assertEqual(result, payload)


if __name__ == "__main__":
    unittest.main()
