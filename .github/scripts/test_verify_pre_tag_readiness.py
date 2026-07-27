#!/usr/bin/env python3
"""Unit tests for the immutable-source pre-tag readiness receipt verifier."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify-pre-tag-readiness.py")
SPEC = importlib.util.spec_from_file_location("verify_pre_tag_readiness", SCRIPT)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)

SOURCE_SHA = "a" * 40


def valid_receipt() -> dict[str, object]:
    return {
        "kind": verifier.KIND,
        "passed": True,
        "source_sha": SOURCE_SHA,
        "lane": "ci",
        "provider_mode": "offline",
        "checks": {name: True for name in verifier.REQUIRED_CHECKS},
    }


class PreTagReadinessReceiptTests(unittest.TestCase):
    def test_valid_exact_sha_offline_receipt_passes(self) -> None:
        self.assertEqual(verifier.verify(valid_receipt(), SOURCE_SHA)["source_sha"], SOURCE_SHA)

    def test_invalid_receipts_fail_closed(self) -> None:
        fixtures = (
            ("wrong source", valid_receipt(), "b" * 40, "!= tag source"),
            ("failed receipt", {**valid_receipt(), "passed": False}, SOURCE_SHA, "did not pass"),
            (
                "missing check",
                {**valid_receipt(), "checks": {name: True for name in verifier.REQUIRED_CHECKS if name != "self_check"}},
                SOURCE_SHA,
                "missing required checks",
            ),
            ("non-offline", {**valid_receipt(), "provider_mode": "production"}, SOURCE_SHA, "offline"),
            ("qualification authority", {**valid_receipt(), "qualified_beta": True}, SOURCE_SHA, "production/qualification"),
        )
        for name, receipt, source_sha, message in fixtures:
            with self.subTest(name=name):
                with self.assertRaisesRegex(verifier.EvidenceError, message):
                    verifier.verify(receipt, source_sha)


if __name__ == "__main__":
    unittest.main()
