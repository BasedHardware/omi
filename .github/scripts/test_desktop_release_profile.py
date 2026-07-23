#!/usr/bin/env python3
from __future__ import annotations

import unittest

import desktop_qualification_evidence as evidence
import desktop_release_profile as profile

SHA = "a" * 40
TAG = "v0.12.99"


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


class QualificationEvidenceBlackboxTests(unittest.TestCase):
    """P2 regression: black-box results must cover both canonical bundle IDs
    so accidentally wiring the same or stale JSON to both --blackbox-result
    and --beta-blackbox-result cannot pass with incomplete coverage."""

    def _make_blackbox_result(self, bundle_id: str) -> dict:
        return {
            "ok": True,
            "release_tag": TAG,
            "source_sha": SHA,
            "bundle_id": bundle_id,
        }

    def _make_release_json(self) -> dict:
        return {"tagName": TAG, "assets": [], "body": ""}

    def _make_profile_evidence(self) -> dict:
        return {
            "schema_version": 1,
            "source_sha": SHA,
            "release_profile": "nightly-rigorous",
            "rigorous_pre_sign_passed": True,
        }

    def _make_files(self) -> dict:
        # build_evidence pops __candidate_gate__ and reads it as JSON before
        # reaching the blackbox checks. Write a valid candidate gate.
        import json
        import tempfile
        from pathlib import Path

        fd, gate_path = tempfile.mkstemp(suffix=".json")
        import os

        os.write(fd, json.dumps({
            "passed": True,
            "release_tag": TAG,
            "source_sha": SHA,
        }).encode())
        os.close(fd)
        # Register cleanup
        self.addCleanup(os.unlink, gate_path)
        return {"__candidate_gate__": Path(gate_path)}

    def test_duplicate_bundle_ids_are_rejected(self) -> None:
        """Both results wired to the stable bundle ID must fail."""
        both_stable = (
            self._make_blackbox_result("com.omi.computer-macos"),
            self._make_blackbox_result("com.omi.computer-macos"),
        )
        with self.assertRaises(ValueError) as ctx:
            evidence.build_evidence(
                self._make_release_json(), TAG, SHA, self._make_files(),
                release_profile_evidence=self._make_profile_evidence(),
                blackbox_results=both_stable,
            )
        self.assertIn("both canonical bundle IDs", str(ctx.exception))

    def test_correct_distinct_bundle_ids_are_accepted(self) -> None:
        """One stable + one beta result should pass the bundle-id check."""
        results = (
            self._make_blackbox_result("com.omi.computer-macos"),
            self._make_blackbox_result("com.omi.computer-macos.beta"),
        )
        # build_evidence will fail later on missing files/assets, but the
        # bundle-ID check must not be the failure point.
        try:
            evidence.build_evidence(
                self._make_release_json(), TAG, SHA, self._make_files(),
                release_profile_evidence=self._make_profile_evidence(),
                blackbox_results=results,
            )
        except ValueError as exc:
            self.assertNotIn("bundle ID", str(exc))


if __name__ == "__main__":
    unittest.main()
