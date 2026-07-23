#!/usr/bin/env python3
from __future__ import annotations

import unittest

import desktop_release_profile as profile

SHA = "a" * 40


class ReleaseProfileTests(unittest.TestCase):
    def test_nightly_requires_truthful_t2_result(self) -> None:
        result = {
            "passed": True,
            "source_sha": SHA,
            "tier": "T2",
            "provider_mode": "offline",
            "fault_suite_passed": True,
        }
        evidence = profile.build_evidence("nightly-rigorous", SHA, result)
        self.assertTrue(evidence["rigorous_pre_sign_passed"])

    def test_manual_fast_records_skipped_rigorous_gate(self) -> None:
        evidence = profile.build_evidence("manual-fast", SHA, None)
        self.assertFalse(evidence["rigorous_pre_sign_passed"])
        self.assertIsNone(evidence["pre_sign_qualification"])

    def test_missing_and_unknown_profiles_fail_closed(self) -> None:
        for value in ("", "nightly", "fast", "stable"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                profile.validate_profile(value)

    def test_nightly_rejects_failed_or_wrong_source_evidence(self) -> None:
        base = {
            "passed": True,
            "source_sha": SHA,
            "tier": "T2",
            "provider_mode": "offline",
            "fault_suite_passed": True,
        }
        for mutation in ({"passed": False}, {"source_sha": "b" * 40}, {"provider_mode": "online"}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                profile.build_evidence("nightly-rigorous", SHA, {**base, **mutation})

    def test_manual_fast_rejects_rigorous_claim(self) -> None:
        with self.assertRaises(ValueError):
            profile.build_evidence("manual-fast", SHA, {"passed": True})


if __name__ == "__main__":
    unittest.main()
