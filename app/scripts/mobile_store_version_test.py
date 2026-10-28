#!/usr/bin/env python3
"""Tests for hermetic mobile store-result parsing and version selection."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("mobile_store_version.py")
SPEC = importlib.util.spec_from_file_location("mobile_store_version", SCRIPT)
assert SPEC and SPEC.loader
store = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = store
SPEC.loader.exec_module(store)


def snapshots(
    *,
    tf: store.StoreSnapshot,
    app: store.StoreSnapshot,
    play: store.StoreSnapshot,
    play_bundles: store.StoreSnapshot | None = None,
) -> dict[str, store.StoreSnapshot]:
    return {
        "testflight": tf,
        "app_store": app,
        "play": play,
        "play_bundles": play_bundles if play_bundles is not None else store.StoreSnapshot.empty("play_bundles"),
    }


class MobileStoreVersionTests(unittest.TestCase):
    def test_blank_successful_reads_are_empty_history(self) -> None:
        self.assertEqual(store.parse_app_store_output("", provider="testflight").status, "empty")
        self.assertEqual(store.parse_play_output("\n").status, "empty")

    def test_failed_reads_are_errors_not_empty_history(self) -> None:
        with self.assertRaisesRegex(store.StoreLookupError, "failed"):
            store.parse_app_store_output("", provider="testflight", returncode=1)
        with self.assertRaisesRegex(store.StoreLookupError, "failed"):
            store.parse_play_output("", returncode=1)
        with self.assertRaisesRegex(store.StoreLookupError, "failed"):
            store.parse_play_bundles_output("[]", returncode=1)

    def test_valid_app_store_and_play_values_parse(self) -> None:
        tf = store.parse_app_store_output(
            '{"version":"1.2.3","buildNumber":"456","buildId":"codemagic-build-123"}',
            provider="testflight",
        )
        play = store.parse_play_output("789\n")
        self.assertEqual((tf.version, tf.build_number), ("1.2.3", 456))
        self.assertEqual(play.build_number, 789)

        app_store = store.parse_app_store_output(
            '{"version":"2.0.0","buildNumber":789,"buildId":"asc-build-456"}',
            provider="app_store",
        )
        self.assertEqual((app_store.version, app_store.build_number), ("2.0.0", 789))

    def test_play_bundle_list_takes_the_highest_uploaded_version_code(self) -> None:
        self.assertEqual(store.parse_play_bundles_output("[]").status, "empty")
        bundles = store.parse_play_bundles_output(
            '[{"versionCode": "1526", "sha1": "a", "sha256": "b"}, {"versionCode": 1527, "sha1": "c", "sha256": "d"}]'
        )
        self.assertEqual((bundles.status, bundles.build_number), ("available", 1527))

    def test_play_bundle_list_blank_and_null_fail_closed(self) -> None:
        # A successful bundles list --json always prints a JSON array, so
        # blank output and null cannot be trusted as empty history.
        for raw in ("", "\n", "null"):
            with self.subTest(raw=raw):
                with self.assertRaises(store.StoreLookupError):
                    store.parse_play_bundles_output(raw)

    def test_malformed_or_zero_store_values_fail_closed(self) -> None:
        cases = (
            lambda: store.parse_app_store_output('{"version":"1.2","buildNumber":"456"}', provider="app_store"),
            lambda: store.parse_app_store_output('{"version":"1.2.3","buildNumber":"0"}', provider="app_store"),
            lambda: store.parse_app_store_output('{"version":"1.2.3","buildNumber":0}', provider="app_store"),
            lambda: store.parse_app_store_output('{"version":"1.2.3","buildNumber":-1}', provider="app_store"),
            lambda: store.parse_play_output("-1"),
            lambda: store.parse_play_output("9" * 100),
            lambda: store.parse_play_bundles_output('[{"versionCode": "0"}]'),
            lambda: store.parse_play_bundles_output('[{"sha1": "a", "sha256": "b"}]'),
            lambda: store.parse_play_bundles_output('[{"versionCode": "1", "unknown": true}]'),
            lambda: store.parse_play_bundles_output('{"versionCode": 1}'),
            lambda: store.parse_play_bundles_output("not json"),
        )
        for case in cases:
            with self.subTest():
                with self.assertRaises(store.StoreLookupError):
                    case()

    def test_empty_history_seeds_from_pubspec_without_zero(self) -> None:
        empty = snapshots(
            tf=store.StoreSnapshot.empty("testflight"),
            app=store.StoreSnapshot.empty("app_store"),
            play=store.StoreSnapshot.empty("play"),
        )
        plan = store.resolve_next_release("android", "1.2.3+456", empty)
        self.assertEqual((plan.version, plan.build_number), ("1.2.3", 456))

    def test_ios_does_not_require_an_android_store_read(self) -> None:
        empty = {"testflight": store.StoreSnapshot.empty("testflight"), "app_store": store.StoreSnapshot.empty("app_store")}
        plan = store.resolve_next_release("ios", "1.2.3+456", empty)
        self.assertEqual((plan.version, plan.build_number), ("1.2.3", 456))

    def test_available_history_bumps_above_every_store(self) -> None:
        values = snapshots(
            tf=store.StoreSnapshot.available("testflight", "1.2.3", 456),
            app=store.StoreSnapshot.available("app_store", "1.2.2", 460),
            play=store.StoreSnapshot.available("play", None, 999),
        )
        plan = store.resolve_next_release("android", "1.0.0+1", values)
        self.assertEqual((plan.version, plan.build_number), ("1.2.3", 1000))

    def test_store_history_is_authoritative_over_a_higher_pubspec_build(self) -> None:
        values = snapshots(
            tf=store.StoreSnapshot.available("testflight", "1.2.3", 900),
            app=store.StoreSnapshot.available("app_store", "1.2.3", 900),
            play=store.StoreSnapshot.available("play", None, 900),
        )
        plan = store.resolve_next_release("android", "1.2.3+992", values)
        self.assertEqual(plan.build_number, 901)

    def test_off_track_play_bundle_advances_build_above_every_track(self) -> None:
        # A rejected Play release leaves its uploaded bundle on no track: the
        # track read still says 1526 while the bundle list sees 1527, and the
        # next build must clear the burned code.
        values = snapshots(
            tf=store.StoreSnapshot.available("testflight", "1.2.3", 456),
            app=store.StoreSnapshot.available("app_store", "1.2.2", 460),
            play=store.StoreSnapshot.available("play", None, 1526),
            play_bundles=store.parse_play_bundles_output('[{"versionCode": "1527", "sha1": "a", "sha256": "b"}]'),
        )
        plan = store.resolve_next_release("android", "1.0.0+1", values)
        self.assertEqual((plan.version, plan.build_number), ("1.2.3", 1528))

    def test_failed_play_bundles_read_exits_nonzero(self) -> None:
        payload = json.dumps(
            {
                "testflight": {"stdout": '{"version":"1.2.3","buildNumber":"456"}', "exit_code": 0},
                "app_store": {"stdout": '{"version":"1.2.2","buildNumber":"460"}', "exit_code": 0},
                "play": {"stdout": "1526", "exit_code": 0},
                "play_bundles": {"stdout": "", "exit_code": 1},
            }
        )
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write(payload)
            input_path = handle.name
        try:
            with self.assertRaises(SystemExit) as raised:
                store.main(
                    ["--platform", "android", "--pubspec-version", "1.2.3+456", "--input", input_path]
                )
            self.assertNotEqual(raised.exception.code, 0)
        finally:
            os.unlink(input_path)

    def test_store_snapshot_set_must_be_complete(self) -> None:
        with self.assertRaises(store.StoreLookupError):
            store.resolve_next_release("ios", "1.2.3+1", {})
        with self.assertRaises(store.StoreLookupError):
            store.resolve_next_release(
                "android",
                "1.2.3+1",
                {
                    "testflight": store.StoreSnapshot.empty("testflight"),
                    "app_store": store.StoreSnapshot.empty("app_store"),
                    "play": store.StoreSnapshot.empty("play"),
                },
            )


if __name__ == "__main__":
    unittest.main()
