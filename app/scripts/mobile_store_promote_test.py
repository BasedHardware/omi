#!/usr/bin/env python3
"""Offline contract tests for manual, exact-build mobile public promotion."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

_SPEC = importlib.util.spec_from_file_location(
    "mobile_store_promote", Path(__file__).with_name("mobile_store_promote.py")
)
promote = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = promote
_SPEC.loader.exec_module(promote)


class InputTests(unittest.TestCase):
    def test_confirmation_and_selected_build_are_required_before_store_calls(self):
        cases = (
            ["--confirm", "no", "--platform", "ios", "--version", "1.2.3", "--ios-build", "11"],
            ["--confirm", "submit-for-review", "--platform", "ios", "--version", "1.2.3"],
            ["--confirm", "submit-for-review", "--platform", "android", "--version", "1.2.3", "--android-build", "0"],
            [
                "--confirm",
                "submit-for-review",
                "--platform",
                "ios",
                "--version",
                "1.2.3",
                "--ios-build",
                "11",
                "--android-build",
                "22",
            ],
            ["--confirm", "submit-for-review", "--platform", "both", "--version", "1.2.3", "--ios-build", "11"],
        )
        with patch.object(promote, "prepare_ios") as ios, patch.object(promote, "prepare_android") as android:
            for argv in cases:
                with self.subTest(argv=argv), patch.object(sys, "argv", ["promote.py", *argv]):
                    self.assertEqual(promote.main(), 1)
            ios.assert_not_called()
            android.assert_not_called()

    def test_missing_release_file_prevents_store_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            with self.assertRaises(promote.PromotionError):
                promote.require_notes(missing, "1.2.3", "ios")


class IOSChecks(unittest.TestCase):
    def test_live_public_version_must_not_be_newer(self):
        response = MagicMock()
        response.__enter__.return_value = response
        with patch.object(promote.urllib.request, "urlopen", return_value=response), patch.object(
            promote.json,
            "load",
            return_value={"resultCount": 1, "results": [{"trackId": 6502156163, "version": "1.2.4"}]},
        ):
            with self.assertRaisesRegex(promote.PromotionError, "older than"):
                promote.check_live_ios_version("1.2.3")

    def test_only_valid_exact_build_is_selected(self):
        build = {
            "data": [
                {"id": "selected-id", "attributes": {"version": "23", "processingState": "VALID", "expired": False}}
            ]
        }
        self.assertEqual(promote.select_ios_build(build, "1.2.3", "23").id, "selected-id")
        build["data"][0]["attributes"]["processingState"] = "PROCESSING"
        with self.assertRaises(promote.PromotionError):
            promote.select_ios_build(build, "1.2.3", "23")
        build["data"][0]["attributes"]["processingState"] = "INVALID"
        with self.assertRaises(promote.PromotionError):
            promote.select_ios_build(build, "1.2.3", "23")
        build["data"][0]["attributes"]["processingState"] = "VALID"
        with self.assertRaises(promote.PromotionError):
            promote.select_ios_build(build, "1.2.3", "22")

    def test_marketing_version_mismatch_blocks_submission(self):
        build = {"data": [{"id": "selected-id", "attributes": {"version": "23", "processingState": "VALID"}}]}
        credentials = {
            "APP_STORE_CONNECT_ISSUER_ID": "test-issuer",
            "APP_STORE_CONNECT_KEY_IDENTIFIER": "test-id",
            "APP_STORE_CONNECT_PRIVATE_KEY": "test-key",
        }
        with patch.dict(promote.os.environ, credentials), patch.object(promote, "check_live_ios_version"), patch.object(
            promote, "check_no_ios_version_in_review"
        ), patch.object(promote, "cli_json", side_effect=[build, {"attributes": {"version": "1.2.4"}}]) as lookup:
            with self.assertRaisesRegex(promote.PromotionError, "marketing version"):
                promote.prepare_ios("1.2.3", "23")
            self.assertEqual(lookup.call_count, 2)

    def _versions_by_state(self, held):
        def lookup(*args):
            state = args[args.index("--state") + 1]
            return {"data": [{"attributes": {"versionString": v}} for v, s in held if s == state]}

        return lookup

    def test_a_version_with_apple_blocks_a_newer_submission_before_any_build_lookup(self):
        for state in promote.IOS_REVIEW_HOLD_STATES:
            with self.subTest(state=state), patch.object(
                promote, "cli_json", side_effect=self._versions_by_state([("1.2.3", state)])
            ):
                with self.assertRaisesRegex(promote.PromotionError, "never withdraw"):
                    promote.check_no_ios_version_in_review("1.2.4")

    def test_prepare_ios_refuses_while_another_version_is_in_review(self):
        credentials = {
            "APP_STORE_CONNECT_ISSUER_ID": "test-issuer",
            "APP_STORE_CONNECT_KEY_IDENTIFIER": "test-id",
            "APP_STORE_CONNECT_PRIVATE_KEY": "test-key",
        }
        calls = []

        def lookup(*args):
            calls.append(args)
            if args[:2] == ("apps", "app-store-versions"):
                state = args[args.index("--state") + 1]
                return {"data": [{"attributes": {"versionString": "1.2.3"}}] if state == "WAITING_FOR_REVIEW" else []}
            raise AssertionError(f"unexpected lookup {args}")

        with patch.dict(promote.os.environ, credentials), patch.object(promote, "check_live_ios_version"), patch.object(
            promote, "cli_json", side_effect=lookup
        ):
            with self.assertRaisesRegex(promote.PromotionError, "1.2.3 WAITING_FOR_REVIEW"):
                promote.prepare_ios("1.2.4", "24")
        self.assertTrue(all(c[:2] == ("apps", "app-store-versions") for c in calls))  # no build was selected

    def test_same_version_in_review_or_nothing_in_flight_is_allowed(self):
        with patch.object(promote, "cli_json", side_effect=self._versions_by_state([("1.2.4", "WAITING_FOR_REVIEW")])):
            promote.check_no_ios_version_in_review("1.2.4")
        with patch.object(promote, "cli_json", side_effect=self._versions_by_state([])):
            promote.check_no_ios_version_in_review("1.2.4")

    def test_submission_identifies_existing_build_and_does_not_upload(self):
        with patch.object(promote.subprocess, "run") as command:
            promote.submit_ios(promote.IOSBuild("selected-id", "1.2.3", "23"), "- New line")
        args = command.call_args.args[0]
        self.assertEqual(args[:3], ["app-store-connect", "builds", "submit-to-app-store"])
        self.assertEqual(args[-1], "selected-id")
        self.assertEqual(args[args.index("--whats-new") + 1], "- New line")
        self.assertNotIn("publish", args)

    def test_locale_aware_submission_writes_whats_new_for_every_locale(self):
        captured = {}

        def fake_run(command, **kwargs):
            path = next(a for a in command if a.startswith("@file:"))[len("@file:") :]
            captured["command"] = command
            captured["payload"] = json.loads(Path(path).read_text(encoding="utf-8"))
            captured["path"] = Path(path)
            return Mock(returncode=0)

        with patch.object(promote.subprocess, "run", side_effect=fake_run):
            promote.submit_ios(promote.IOSBuild("selected-id", "1.2.3", "23"), "- New line", locales=["fr-FR", "en-US"])
        args = captured["command"]
        self.assertNotIn("--whats-new", args)
        self.assertIn("--no-phased-release", args)
        self.assertEqual(args[args.index("--release-type") + 1], "MANUAL")
        self.assertEqual(args[-1], "selected-id")
        self.assertEqual(
            captured["payload"],
            [{"locale": "en-US", "whats_new": "- New line"}, {"locale": "fr-FR", "whats_new": "- New line"}],
        )
        self.assertFalse(captured["path"].exists())
        with self.assertRaises(promote.PromotionError):
            promote.ios_localizations([], "- New line")

    def test_live_locales_come_from_the_newest_live_version(self):
        def lookup(*args):
            if args[:2] == ("apps", "app-store-versions"):
                return [
                    {"id": "v1", "attributes": {"versionString": "1.0"}},
                    {"id": "v562", "attributes": {"versionString": "1.0.562"}},
                    {"id": "v563", "attributes": {"versionString": "1.0.563"}},
                ]
            self.assertEqual(args, ("app-store-versions", "localizations", "v563"))
            return {"data": [{"attributes": {"locale": "en-US"}}, {"attributes": {"locale": "fr-FR"}}, {"attributes": {"locale": "en-US"}}]}

        with patch.object(promote, "cli_json", side_effect=lookup):
            self.assertEqual(promote.ios_live_locales(), ["en-US", "fr-FR"])

    def test_live_locales_fail_closed_without_a_live_version_or_locales(self):
        with patch.object(promote, "cli_json", return_value=[]):
            with self.assertRaisesRegex(promote.PromotionError, "no live iOS version"):
                promote.ios_live_locales()

        def no_locales(*args):
            return [{"id": "v1", "attributes": {"versionString": "1.0.1"}}] if args[0] == "apps" else []

        with patch.object(promote, "cli_json", side_effect=no_locales):
            with self.assertRaisesRegex(promote.PromotionError, "no localizations"):
                promote.ios_live_locales()

    def test_rejected_submission_reports_apple_reason(self):
        error = subprocess.CalledProcessError(1, ["app-store-connect"], stderr="409: missing whatsNew for de-DE")
        with patch.object(promote.subprocess, "run", side_effect=error):
            with self.assertRaisesRegex(promote.PromotionError, "missing whatsNew for de-DE"):
                promote.submit_ios(promote.IOSBuild("selected-id", "1.2.3", "23"), "- New line", locales=["de-DE"])


class AndroidChecks(unittest.TestCase):
    def setUp(self):
        self.alpha = {"track": "alpha", "releases": [{"name": "1.2.3", "versionCodes": ["23"], "status": "completed"}]}
        self.production = {
            "track": "production",
            "releases": [{"name": "1.2.2", "versionCodes": ["22"], "status": "completed"}],
        }

    def test_only_alpha_exact_version_and_code_are_eligible(self):
        promote.select_play_release(self.alpha, self.production, "1.2.3", "23")
        # Play Console names a release "X.Y.Z (code)"; the version inside must still match exactly.
        promote.select_play_release(
            {"track": "alpha", "releases": [{"name": "1.2.3 (23)", "versionCodes": ["23"], "status": "completed"}]},
            self.production,
            "1.2.3",
            "23",
        )
        internal = {"track": "internal", "releases": self.alpha["releases"]}
        promote.select_play_release(internal, self.production, "1.2.3", "23", source_track="internal")
        with self.assertRaisesRegex(promote.PromotionError, "internal track lookup failed"):
            promote.select_play_release(self.alpha, self.production, "1.2.3", "23", source_track="internal")
        for release in (
            {"name": "1.2.4", "versionCodes": ["23"], "status": "completed"},
            {"name": "1.2.3", "versionCodes": ["23", "24"], "status": "completed"},
            {"name": "1.2.3", "versionCodes": ["23"], "status": "draft"},
        ):
            with self.subTest(release=release):
                with self.assertRaises(promote.PromotionError):
                    promote.select_play_release(
                        {"track": "alpha", "releases": [release]}, self.production, "1.2.3", "23"
                    )

    def test_public_marketing_version_is_a_roll_forward_floor(self):
        self.production["releases"][0]["name"] = "1.2.4"
        with self.assertRaisesRegex(promote.PromotionError, "older than"):
            promote.select_play_release(self.alpha, self.production, "1.2.3", "23")
        self.production["releases"][0]["name"] = "1.2.4 (30)"
        with self.assertRaises(promote.PromotionError):
            promote.select_play_release(self.alpha, self.production, "1.2.3", "23")
        self.production["releases"][0]["name"] = "1.2.2 (22)"
        promote.select_play_release(self.alpha, self.production, "1.2.3", "23")
        self.production["releases"][0]["name"] = "not-a-version"
        promote.select_play_release(self.alpha, self.production, "1.2.3", "23")

    def test_production_release_version_parses_play_console_names(self) -> None:
        self.assertEqual(promote.production_release_version("1.0.552"), "1.0.552")
        self.assertEqual(promote.production_release_version("1.0.552 (1246)"), "1.0.552")
        self.assertIsNone(promote.production_release_version("not-a-version"))
        self.assertIsNone(promote.production_release_version("1.0"))

    def test_promotion_updates_only_production_using_existing_code_and_derived_notes(self):
        client = Mock()
        promote.submit_android(client, "edit-id", "1.2.3", "23", "New line")
        client.edits().tracks().update.assert_called_once_with(
            packageName="com.friend.ios",
            editId="edit-id",
            track="production",
            body={
                "track": "production",
                "releases": [
                    {
                        "name": "1.2.3",
                        "versionCodes": ["23"],
                        "status": "completed",
                        "releaseNotes": [{"language": "en-US", "text": "New line"}],
                    }
                ],
            },
        )
        client.edits().commit.assert_called_once_with(packageName="com.friend.ios", editId="edit-id")
        self.assertFalse(client.edits().bundles.upload.called)

    def test_staged_and_halted_are_the_alternatives_to_completed(self):
        client = Mock()
        promote.submit_android(client, "edit-id", "1.2.3", "23", "New line", status="draft")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["status"], "draft")
        self.assertEqual(body["releases"][0]["versionCodes"], ["23"])
        client.edits().commit.assert_called_once()
        # staged rollout: inProgress WITH a fraction is legal; without one it is not
        promote.submit_android(Mock(), "edit-id", "1.2.3", "23", "New line", status="inProgress", user_fraction=0.05)
        with self.assertRaises(promote.PromotionError):
            promote.submit_android(Mock(), "edit-id", "1.2.3", "23", "New line", status="inProgress")
        with self.assertRaises(promote.PromotionError):
            promote.submit_android(Mock(), "edit-id", "1.2.3", "23", "New line", status="reclaimed")
        with self.assertRaises(promote.PromotionError):
            promote.submit_android(Mock(), "edit-id", "1.2.3", "23", "New line", status="completed", user_fraction=0.05)

    def test_extra_codes_are_retained_and_must_be_unique(self):
        client = Mock()
        promote.submit_android(
            client, "edit-id", "1.2.3", "23", "New line", status="inProgress", user_fraction=0.25, extra_codes=("22",)
        )
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["versionCodes"], ["23", "22"])
        client.edits().commit.assert_called_once()
        with self.assertRaisesRegex(promote.PromotionError, "unique"):
            promote.submit_android(
                Mock(), "edit-id", "1.2.3", "23", "New line", status="inProgress", user_fraction=0.25, extra_codes=("23",)
            )

    def test_advancing_a_base_release_preserves_its_metadata(self):
        client = Mock()
        staged = {
            "name": "1.2.3 (23)",
            "versionCodes": ["23"],
            "status": "inProgress",
            "userFraction": 0.05,
            "countryTargeting": {"countries": ["US", "CA"]},
            "inAppUpdatePriority": 3,
            "releaseNotes": [
                {"language": "en-US", "text": "Shipped"},
                {"language": "de-DE", "text": "Ausgeliefert"},
            ],
        }
        promote.submit_android(
            client, "edit-id", "1.2.3", "23", "ignored when notes exist", status="inProgress", user_fraction=0.25,
            base_release=staged,
        )
        release = client.edits().tracks().update.call_args.kwargs["body"]["releases"][0]
        self.assertEqual(release["countryTargeting"], {"countries": ["US", "CA"]})
        self.assertEqual(release["inAppUpdatePriority"], 3)
        self.assertEqual(
            release["releaseNotes"],
            [{"language": "en-US", "text": "Shipped"}, {"language": "de-DE", "text": "Ausgeliefert"}],
        )
        self.assertEqual(release["userFraction"], 0.25)
        self.assertEqual(release["versionCodes"], ["23"])
        self.assertEqual(release["name"], "1.2.3")
        client.edits().commit.assert_called_once()

    def test_advancing_a_base_release_without_notes_uses_derived_notes(self):
        client = Mock()
        staged = {"name": "1.2.3 (23)", "versionCodes": ["23"], "status": "inProgress", "userFraction": 0.05}
        promote.submit_android(
            client, "edit-id", "1.2.3", "23", "Derived line", status="completed", base_release=staged
        )
        release = client.edits().tracks().update.call_args.kwargs["body"]["releases"][0]
        self.assertEqual(release["releaseNotes"], [{"language": "en-US", "text": "Derived line"}])
        self.assertNotIn("userFraction", release)
        client.edits().commit.assert_called_once()

    def test_completion_drops_country_targeting_but_a_hop_keeps_it(self):
        client = Mock()
        staged = {
            "name": "1.2.3 (23)",
            "versionCodes": ["23"],
            "status": "inProgress",
            "userFraction": 0.05,
            "countryTargeting": {"countries": ["US"]},
        }
        # Google permits countryTargeting only on inProgress releases: a
        # mid-ladder hop keeps it, the completing PUT must drop it.
        promote.submit_android(
            client, "edit-id", "1.2.3", "23", "n", status="inProgress", user_fraction=0.25, base_release=dict(staged)
        )
        hop = client.edits().tracks().update.call_args.kwargs["body"]["releases"][0]
        self.assertEqual(hop["countryTargeting"], {"countries": ["US"]})
        promote.submit_android(client, "edit-id", "1.2.3", "23", "n", status="completed", base_release=dict(staged))
        done = client.edits().tracks().update.call_args.kwargs["body"]["releases"][0]
        self.assertNotIn("countryTargeting", done)
        self.assertNotIn("userFraction", done)


if __name__ == "__main__":
    unittest.main()
