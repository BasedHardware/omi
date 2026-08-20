#!/usr/bin/env python3
"""Regression tests for associated-PR body loading used by Release Eligibility."""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

SCRIPT_DIR = Path(__file__).resolve().parent
import importlib.util

spec = importlib.util.spec_from_file_location(
    "load_associated_pr_bodies", SCRIPT_DIR / "load_associated_pr_bodies.py"
)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class LoadAssociatedPrBodiesTests(unittest.TestCase):
    def test_concatenates_associated_pr_bodies(self) -> None:
        payload = [
            {"number": 11553, "body": "Line-Count-Exception: a.swift | 1500 -> 1510 | layout"},
            {"number": 11556, "body": "Line-Count-Exception: b.swift | 1600 -> 1625 | citation"},
        ]
        opener = MagicMock(return_value=_FakeResponse(json.dumps(payload).encode("utf-8")))

        body = mod.associated_pr_bodies("BasedHardware/omi", "abc123", "token", opener=opener)

        self.assertIn("Line-Count-Exception: a.swift", body)
        self.assertIn("Line-Count-Exception: b.swift", body)
        request = opener.call_args.args[0]
        self.assertIn("/commits/abc123/pulls", request.full_url)

    def test_empty_payload_writes_empty_body(self) -> None:
        opener = MagicMock(return_value=_FakeResponse(b"[]"))
        body = mod.associated_pr_bodies("BasedHardware/omi", "abc123", "token", opener=opener)
        self.assertEqual(body, "")

    def test_missing_token_fails_closed(self) -> None:
        with self.assertRaises(RuntimeError):
            mod.associated_pr_bodies("BasedHardware/omi", "abc123", "")


if __name__ == "__main__":
    unittest.main()
