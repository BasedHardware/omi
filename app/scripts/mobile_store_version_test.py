#!/usr/bin/env python3
"""Tests for hermetic mobile store-result parsing and version selection."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT = Path(__file__).with_name("mobile_store_version.py")
SPEC = importlib.util.spec_from_file_location("mobile_store_version", SCRIPT)
assert SPEC and SPEC.loader
store = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = store
SPEC.loader.exec_module(store)


def snapshots(*, tf: store.StoreSnapshot, app: store.StoreSnapshot, play: store.StoreSnapshot) -> dict[str, store.StoreSnapshot]:
    return {"testflight": tf, "app_store": app, "play": play}


class MobileStoreVersionTests(unittest.TestCase):
    def test_blank_successful_reads_are_empty_history(self) -> None:
        self.assertEqual(store.parse_app_store_output("", provider="testflight").status, "empty")
        self.assertEqual(store.parse_play_output("\n").status, "empty")

    def test_failed_reads_are_errors_not_empty_history(self) -> None:
        with self.assertRaisesRegex(store.StoreLookupError, "failed"):
            store.parse_app_store_output("", provider="testflight", returncode=1)
        with self.assertRaisesRegex(store.StoreLookupError, "failed"):
            store.parse_play_output("", returncode=1)

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

    def test_malformed_or_zero_store_values_fail_closed(self) -> None:
        cases = (
            lambda: store.parse_app_store_output('{"version":"1.2","buildNumber":"456"}', provider="app_store"),
            lambda: store.parse_app_store_output('{"version":"1.2.3","buildNumber":"0"}', provider="app_store"),
            lambda: store.parse_app_store_output('{"version":"1.2.3","buildNumber":0}', provider="app_store"),
            lambda: store.parse_app_store_output('{"version":"1.2.3","buildNumber":-1}', provider="app_store"),
            lambda: store.parse_play_output("-1"),
            lambda: store.parse_play_output("9" * 100),
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

    def test_store_snapshot_set_must_be_complete(self) -> None:
        with self.assertRaises(store.StoreLookupError):
            store.resolve_next_release("ios", "1.2.3+1", {})


if __name__ == "__main__":
    unittest.main()
