#!/usr/bin/env python3
"""Tests for the strict mobile release identity contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).with_name("mobile_release_identity.py")
SPEC = importlib.util.spec_from_file_location("mobile_release_identity", SCRIPT)
assert SPEC and SPEC.loader
identity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = identity
SPEC.loader.exec_module(identity)

SHA = "a" * 40
OTHER_SHA = "b" * 40


class MobileReleaseIdentityTests(unittest.TestCase):
    def test_all_supported_suffixes_parse(self) -> None:
        for suffix in ("mobile", "ios", "android"):
            with self.subTest(suffix=suffix):
                parsed = identity.parse_release_tag(f"v1.2.3+456-{suffix}-cm")
                self.assertEqual(parsed, ("1.2.3", 456, suffix))

    def test_platform_specific_tags_resolve_to_the_requested_platform(self) -> None:
        ios = identity.resolve_release_identity("v1.2.3+456-ios-cm", "ios")
        android = identity.resolve_release_identity("v1.2.3+456-android-cm", "android")
        self.assertEqual((ios.version, ios.build_number, ios.platform), ("1.2.3", 456, "ios"))
        self.assertEqual((android.version, android.build_number, android.platform), ("1.2.3", 456, "android"))

    def test_legacy_mobile_tag_resolves_for_both_platforms(self) -> None:
        self.assertEqual(identity.resolve_release_identity("v1.2.3+456-mobile-cm", "ios").platform, "ios")
        self.assertEqual(identity.resolve_release_identity("v1.2.3+456-mobile-cm", "android").platform, "android")

    def test_rejects_malformed_tags(self) -> None:
        malformed = (
            "1.2.3+456-ios-cm",
            "v1.2+456-ios-cm",
            "v1.2.3+456-ios",
            "v1.2.3+456-ios-cm-extra",
            "v01.2.3+456-ios-cm",
            "v1.2.3+456.0-ios-cm",
        )
        for tag in malformed:
            with self.subTest(tag=tag):
                with self.assertRaises(identity.ReleaseIdentityError):
                    identity.parse_release_tag(tag)

    def test_rejects_wrong_platform_tags(self) -> None:
        with self.assertRaisesRegex(identity.ReleaseIdentityError, "does not match"):
            identity.resolve_release_identity("v1.2.3+456-ios-cm", "android")
        with self.assertRaisesRegex(identity.ReleaseIdentityError, "does not match"):
            identity.resolve_release_identity("v1.2.3+456-android-cm", "ios")

    def test_rejects_zero_negative_and_huge_builds(self) -> None:
        for build in ("0", "-1", str(identity.MAX_BUILD_NUMBER + 1), "9" * 100):
            with self.subTest(build=build):
                with self.assertRaises(identity.ReleaseIdentityError):
                    identity.parse_release_tag(f"v1.2.3+{build}-ios-cm")

    def test_source_identity_accepts_matching_annotated_tag_commit(self) -> None:
        resolved = identity.resolve_release_identity(
            "v1.2.3+456-ios-cm", "ios", source_sha=SHA, tag_source_sha=SHA
        )
        self.assertEqual(resolved.source_sha, SHA)
        self.assertEqual(resolved.tag_source_sha, SHA)

    def test_source_identity_rejects_mismatch(self) -> None:
        with self.assertRaisesRegex(identity.ReleaseIdentityError, "does not match"):
            identity.resolve_release_identity(
                "v1.2.3+456-ios-cm", "ios", source_sha=SHA, tag_source_sha=OTHER_SHA
            )

    def test_cli_returns_machine_readable_identity(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--tag",
                "v1.2.3+456-android-cm",
                "--platform",
                "android",
                "--format",
                "json",
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(json.loads(result.stdout)["build_number"], 456)

    def test_invalid_identity_fails_before_a_following_command(self) -> None:
        marker = SCRIPT.with_suffix(".identity-test-marker")
        marker.unlink(missing_ok=True)
        try:
            result = subprocess.run(
                ["sh", "-c", f"{sys.executable} {SCRIPT} --tag v1.2.3+0-ios-cm --platform ios && touch {marker}"],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
        finally:
            marker.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
