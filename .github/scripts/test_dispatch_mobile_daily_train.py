#!/usr/bin/env python3
"""Offline tests for the daily train dispatcher."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dispatch_mobile_daily_train as dispatcher  # noqa: E402


class DispatchTests(unittest.TestCase):
    def test_payload_targets_the_train_on_main_with_a_non_empty_dry_run_flag(self):
        payload = dispatcher.build_payload("app-1", dry_run=False)
        self.assertEqual(payload["workflowId"], "mobile-daily-train")
        self.assertEqual(payload["branch"], "main")
        self.assertEqual(payload["environment"]["variables"], {"TRAIN_DRY_RUN": "false"})
        self.assertEqual(dispatcher.build_payload("app-1", dry_run=True)["environment"]["variables"], {"TRAIN_DRY_RUN": "true"})
        with self.assertRaises(dispatcher.DispatchError):
            dispatcher.build_payload("", dry_run=False)

    def test_payload_carries_the_gate_pins_when_supplied(self):
        payload = dispatcher.build_payload("app-1", dry_run=False, pin_ios="1.0.554/1334", pin_android="1.0.554/1340")
        self.assertEqual(
            payload["environment"]["variables"],
            {"TRAIN_DRY_RUN": "false", "TRAIN_PIN_IOS": "1.0.554/1334", "TRAIN_PIN_ANDROID": "1.0.554/1340"},
        )
        # Pins are optional: an unpinned dispatch keeps the variables non-empty-only.
        bare = dispatcher.build_payload("app-1", dry_run=False)
        self.assertNotIn("TRAIN_PIN_IOS", bare["environment"]["variables"])
        self.assertNotIn("TRAIN_PIN_ANDROID", bare["environment"]["variables"])

    def test_payload_accepts_none_as_an_audited_no_candidate(self):
        payload = dispatcher.build_payload("app-1", dry_run=False, pin_android="none")
        self.assertEqual(payload["environment"]["variables"]["TRAIN_PIN_ANDROID"], "none")
        with self.assertRaisesRegex(dispatcher.DispatchError, "X.Y.Z/build, none, or empty"):
            dispatcher.build_payload("app-1", dry_run=False, pin_ios="1.0.554")

    def test_dispatch_passes_pins_through_to_the_build(self):
        with patch.object(dispatcher, "_api_post", return_value={"buildId": "b-1"}) as post:
            self.assertEqual(
                dispatcher.dispatch("app-1", "token", dry_run=False, pin_ios="1.0.554/1334"),
                "b-1",
            )
        self.assertEqual(post.call_args.args[2]["environment"]["variables"]["TRAIN_PIN_IOS"], "1.0.554/1334")
        self.assertNotIn("TRAIN_PIN_ANDROID", post.call_args.args[2]["environment"]["variables"])

    def test_dispatch_requires_a_build_id(self):
        with patch.object(dispatcher, "_api_post", return_value={"buildId": "b-1"}) as post:
            self.assertEqual(dispatcher.dispatch("app-1", "token", dry_run=True), "b-1")
        self.assertEqual(post.call_args.args[0], dispatcher.BUILDS_API)
        self.assertEqual(post.call_args.args[2]["environment"]["variables"]["TRAIN_DRY_RUN"], "true")
        with patch.object(dispatcher, "_api_post", return_value={}):
            with self.assertRaisesRegex(dispatcher.DispatchError, "buildId"):
                dispatcher.dispatch("app-1", "token", dry_run=False)

    def test_a_capture_health_override_travels_only_when_given(self):
        variables = dispatcher.build_payload("app-1", dry_run=False)["environment"]["variables"]
        self.assertNotIn("TRAIN_CAPTURE_HEALTH_OVERRIDE", variables)
        variables = dispatcher.build_payload("app-1", dry_run=False, capture_health_override="noise, DZ")[
            "environment"
        ]["variables"]
        self.assertEqual(variables["TRAIN_CAPTURE_HEALTH_OVERRIDE"], "noise, DZ")
        with patch.dict(os.environ, {"CODEMAGIC_API_TOKEN": "t"}), patch.object(
            dispatcher, "_api_post", return_value={"buildId": "b-1"}
        ) as post:
            self.assertEqual(
                dispatcher.main(["--app-id", "app-1", "--capture-health-override", "why", "--pin-ios", "1.0.566/1417"]), 0
            )
        sent = post.call_args.args[2]["environment"]["variables"]
        self.assertEqual(sent["TRAIN_CAPTURE_HEALTH_OVERRIDE"], "why")
        self.assertEqual(sent["TRAIN_PIN_IOS"], "1.0.566/1417")

    def test_main_fails_without_a_token_and_before_any_request(self):
        with patch.dict(os.environ, {"CODEMAGIC_API_TOKEN": ""}), patch.object(dispatcher, "_api_post") as post:
            self.assertEqual(dispatcher.main(["--app-id", "app-1"]), 1)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
