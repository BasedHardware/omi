#!/usr/bin/env python3
"""Offline tests for the rollout-hop capture-health check (no network)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("mobile_capture_health", Path(__file__).with_name("mobile_capture_health.py"))
health = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = health
_SPEC.loader.exec_module(health)

S = health.BuildStats
H = health.WINDOW_HOURS


def per_window(per_day: float) -> float:
    """Wedge users over the window for a given daily rate."""
    return per_day * H / 24.0


class FakePostHog:
    """Answers the pendant query, then the wedge query; records the HogQL."""

    def __init__(self, pendant: list, wedges: list, error: Exception | None = None):
        self.pendant = pendant
        self.wedges = wedges
        self.error = error
        self.queries: list[str] = []

    def __call__(self, hogql: str) -> list:
        self.queries.append(hogql)
        if self.error:
            raise self.error
        return self.pendant if "Device Session Ended" in hogql else self.wedges


class JudgeTests(unittest.TestCase):
    def test_the_1_0_560_regression_is_bad_against_the_build_below_it(self):
        # iOS build 1354 (1.0.560): 146 of 615 pendant users wedged in its first
        # days; 1349 (1.0.559), the largest build below it, had none.
        stats = {("iOS", "1354"): S(40, 615, "1.0.560"), ("iOS", "1349"): S(0, 809, "1.0.559")}
        verdict = health.judge(stats, "iOS", "1354")
        self.assertTrue(verdict.hold)
        self.assertIn("more than 2x the previous build", verdict.reason)
        self.assertIn("previous build 1349", verdict.reason)

    def test_more_than_fifty_wedge_users_a_day_is_bad(self):
        stats = {("Android", "1461"): S(per_window(60), 5000, "1.0.566"), ("Android", "1445"): S(per_window(60), 5000, "1.0.564")}
        verdict = health.judge(stats, "Android", "1461")
        self.assertTrue(verdict.hold)
        self.assertIn("over the 50/day cap", verdict.reason)

    def test_the_previous_build_is_the_lower_build_with_the_most_pendant_users(self):
        # The operator gate's rule (omi_capture_wedge.previous_build): the store
        # build being replaced has the most pendant users below the candidate.
        # A thin intermediate build (1417 here) is not the baseline.
        stats = {
            ("iOS", "1420"): S(30, 1000, "1.0.567"),
            ("iOS", "1417"): S(5, 300, "1.0.566"),
            ("iOS", "1409"): S(20, 1200, "1.0.565"),
            ("iOS", "1430"): S(0, 5000, "1.0.568"),  # higher: never a baseline
            ("iOS", "1401"): S(0, 10, "1.0.564"),  # under the floor
            ("Android", "1400"): S(0, 9000, "1.0.558"),  # other platform
        }
        prev_build, prev = health.previous_build(stats, "iOS", "1420")
        self.assertEqual(prev_build, "1409")
        # 3.0% vs 1.7%: under 2x, so not bad.
        self.assertFalse(health.judge(stats, "iOS", "1420").hold)

    def test_twice_the_previous_rate_is_bad_and_less_is_not(self):
        base = ("iOS", "1409"), S(20, 1000, "1.0.565")
        self.assertTrue(health.judge(dict([base, (("iOS", "1417"), S(41, 1000, "1.0.566"))]), "iOS", "1417").hold)
        self.assertFalse(health.judge(dict([base, (("iOS", "1417"), S(39, 1000, "1.0.566"))]), "iOS", "1417").hold)

    def test_two_wedge_users_against_a_zero_baseline_are_noise(self):
        stats = {("iOS", "1417"): S(2, 400, "1.0.566"), ("iOS", "1409"): S(0, 1000, "1.0.565")}
        self.assertFalse(health.judge(stats, "iOS", "1417").hold)

    def test_a_thin_build_is_reported_not_compared(self):
        stats = {("iOS", "1417"): S(4, 12, "1.0.566"), ("iOS", "1409"): S(0, 1000, "1.0.565")}
        verdict = health.judge(stats, "iOS", "1417")
        self.assertFalse(verdict.hold)
        self.assertIn("thin sample", verdict.reason)

    def test_a_build_with_no_pendant_sessions_holds(self):
        self.assertTrue(health.judge({}, "iOS", "1417").hold)
        self.assertTrue(health.judge({("iOS", "1417"): S(3, 0, None)}, "iOS", "1417").hold)


class StatsTests(unittest.TestCase):
    PENDANT = [["iOS", "1417", "1.0.566", 600], ["iOS", "1416", "1.0.566", 3], ["iOS", "1409", "1.0.565", 1200],
               ["Android", "1461", "1.0.566", 380]]
    WEDGES = [["iOS", "1417", 66.6], ["Android", "1461", 50.0], ["iOS", "1300", 1.0]]

    def test_stats_join_pendant_users_and_reweighted_wedges(self):
        posthog = FakePostHog(self.PENDANT, self.WEDGES)
        stats = health.build_stats(posthog)
        self.assertEqual(stats[("iOS", "1417")], S(66.6, 600, "1.0.566"))
        self.assertEqual(stats[("iOS", "1409")], S(0.0, 1200, "1.0.565"))
        self.assertEqual(stats[("iOS", "1300")], S(1.0, 0, None))
        pendant_sql, wedge_sql = posthog.queries
        self.assertIn("toString(properties['$app_build'])", pendant_sql)
        self.assertIn("'connected_no_bytes', 'connected_not_capturing'", wedge_sql)
        self.assertIn("omi_sample_pct", wedge_sql)

    def test_identifiers_are_validated_before_they_reach_hogql(self):
        with self.assertRaises(health.CaptureHealthError):
            health._identifier("x' OR 1=1 --")


class CheckRolloutTests(unittest.TestCase):
    # Live 10-20 shape: iOS 1417 and Android 1461 were BAD against the builds below.
    BAD = FakePostHog(
        [["iOS", "1417", "1.0.566", 600], ["iOS", "1409", "1.0.565", 1200], ["Android", "1461", "1.0.566", 380],
         ["Android", "1445", "1.0.564", 340]],
        [["iOS", "1417", 120.0], ["iOS", "1409", 40.0], ["Android", "1461", 50.0]],
    )

    def test_no_key_fails_closed(self):
        verdict = health.check_rollout("ios", build="1417", env={})
        self.assertTrue(verdict.hold)
        self.assertIn("POSTHOG_PERSONAL_API_KEY is not configured", verdict.reason)

    def test_any_read_failure_holds_instead_of_crashing_the_train(self):
        import http.client

        for error in (http.client.IncompleteRead(b""), OSError("reset"), UnicodeDecodeError("utf-8", b"", 0, 1, "x")):
            verdict = health.check_rollout("android", build="1461", env={}, runner=FakePostHog([], [], error=error))
            self.assertTrue(verdict.hold, repr(error))

    def test_a_query_error_fails_closed(self):
        broken = FakePostHog([], [], error=health.CaptureHealthError("PostHog query failed: 503"))
        verdict = health.check_rollout("ios", build="1417", env={}, runner=broken)
        self.assertTrue(verdict.hold)
        self.assertIn("failing closed", verdict.reason)

    def test_a_missing_or_unknown_build_fails_closed(self):
        self.assertTrue(health.check_rollout("android", build=None, env={}, runner=self.BAD).hold)
        self.assertTrue(health.check_rollout("ios", build="", env={}, runner=self.BAD).hold)
        self.assertTrue(health.check_rollout("android", build="9999", env={}, runner=self.BAD).hold)

    def test_both_platforms_hold_a_bad_build_and_the_override_lets_one_run_through(self):
        ios = health.check_rollout("ios", build="1417", env={}, runner=self.BAD)
        android = health.check_rollout("android", build="1461", env={}, runner=self.BAD)
        self.assertTrue(ios.hold, ios.reason)
        self.assertIn("iOS 1417", ios.reason)
        self.assertTrue(android.hold, android.reason)
        verdict = health.check_rollout(
            "android", build="1461", env={health.OVERRIDE_ENV: "known telemetry noise, DZ 10-21"}, runner=self.BAD
        )
        self.assertFalse(verdict.hold)
        self.assertIn("OVERRIDDEN", verdict.reason)
        self.assertIn("known telemetry noise", verdict.reason)


if __name__ == "__main__":
    unittest.main()
