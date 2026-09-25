#!/usr/bin/env python3
"""Offline contract tests for manual, exact-build mobile public promotion."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

_SPEC = importlib.util.spec_from_file_location("mobile_store_promote", Path(__file__).with_name("mobile_store_promote.py"))
promote = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = promote
_SPEC.loader.exec_module(promote)


class InputTests(unittest.TestCase):
    def test_confirmation_and_selected_build_are_required_before_store_calls(self):
        cases = (
            ["--confirm", "no", "--platform", "ios", "--version", "1.2.3", "--ios-build", "11"],
            ["--confirm", "submit-for-review", "--platform", "ios", "--version", "1.2.3"],
            ["--confirm", "submit-for-review", "--platform", "android", "--version", "1.2.3", "--android-build", "0"],
            ["--confirm", "submit-for-review", "--platform", "ios", "--version", "1.2.3", "--ios-build", "11", "--android-build", "22"],
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
            promote.json, "load", return_value={"resultCount": 1, "results": [{"trackId": 6502156163, "version": "1.2.4"}]}
        ):
            with self.assertRaisesRegex(promote.PromotionError, "older than"):
                promote.check_live_ios_version("1.2.3")

    def test_only_valid_exact_build_is_selected(self):
        build = {"data": [{"id": "selected-id", "attributes": {"version": "23", "processingState": "VALID", "expired": False}}]}
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
            "APP_STORE_CONNECT_ISSUER_ID": "test-issuer", "APP_STORE_CONNECT_KEY_IDENTIFIER": "test-id",
            "APP_STORE_CONNECT_PRIVATE_KEY": "test-key",
        }
        with patch.dict(promote.os.environ, credentials), patch.object(promote, "check_live_ios_version"), patch.object(
            promote, "cli_json", side_effect=[build, {"attributes": {"version": "1.2.4"}}]
        ) as lookup:
            with self.assertRaisesRegex(promote.PromotionError, "marketing version"):
                promote.prepare_ios("1.2.3", "23")
            self.assertEqual(lookup.call_count, 2)

    def test_submission_identifies_existing_build_and_does_not_upload(self):
        with patch.object(promote.subprocess, "run") as command:
            promote.submit_ios(promote.IOSBuild("selected-id", "1.2.3", "23"), "- New line")
        args = command.call_args.args[0]
        self.assertEqual(args[:3], ["app-store-connect", "builds", "submit-to-app-store"])
        self.assertEqual(args[-1], "selected-id")
        self.assertEqual(args[args.index("--whats-new") + 1], "- New line")
        self.assertNotIn("publish", args)


class AndroidChecks(unittest.TestCase):
    def setUp(self):
        self.alpha = {"track": "alpha", "releases": [{"name": "1.2.3", "versionCodes": ["23"], "status": "completed"}]}
        self.production = {"track": "production", "releases": [{"name": "1.2.2", "versionCodes": ["22"], "status": "completed"}]}

    def test_only_alpha_exact_version_and_code_are_eligible(self):
        promote.select_play_release(self.alpha, self.production, "1.2.3", "23")
        for release in (
            {"name": "1.2.4", "versionCodes": ["23"], "status": "completed"},
            {"name": "1.2.3", "versionCodes": ["23", "24"], "status": "completed"},
            {"name": "1.2.3", "versionCodes": ["23"], "status": "draft"},
        ):
            with self.subTest(release=release):
                with self.assertRaises(promote.PromotionError):
                    promote.select_play_release({"track": "alpha", "releases": [release]}, self.production, "1.2.3", "23")

    def test_public_marketing_version_is_a_roll_forward_floor(self):
        self.production["releases"][0]["name"] = "1.2.4"
        with self.assertRaisesRegex(promote.PromotionError, "older than"):
            promote.select_play_release(self.alpha, self.production, "1.2.3", "23")
        self.production["releases"][0]["name"] = "not-a-version"
        with self.assertRaises(promote.PromotionError):
            promote.select_play_release(self.alpha, self.production, "1.2.3", "23")

    def test_promotion_updates_only_production_using_existing_code_and_derived_notes(self):
        client = Mock()
        promote.submit_android(client, "edit-id", "1.2.3", "23", "New line")
        client.edits().tracks().update.assert_called_once_with(
            packageName="com.friend.ios", editId="edit-id", track="production",
            body={"track": "production", "releases": [{
                "name": "1.2.3", "versionCodes": ["23"], "status": "completed",
                "releaseNotes": [{"language": "en-US", "text": "New line"}],
            }]},
        )
        client.edits().commit.assert_called_once_with(packageName="com.friend.ios", editId="edit-id")
        self.assertFalse(client.edits().bundles.upload.called)


if __name__ == "__main__":
    unittest.main()
