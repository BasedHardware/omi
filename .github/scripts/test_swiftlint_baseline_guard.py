#!/usr/bin/env python3
"""Adversarial fixture tests for the SwiftLint baseline guard (#9843 Ticket 07).

Tests the down-only baseline ratchet and the swiftlint:disable policy with
fixtures for: addition (rejected), removal (allowed), reorder (allowed),
anonymous/blanket suppression (rejected), multi-rule without reason (rejected),
and valid reasoned suppression (allowed).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GUARD_PATH = Path(__file__).resolve().parents[2] / "desktop/macos/scripts/check-swiftlint-baseline.py"


def _load_guard():
  spec = importlib.util.spec_from_file_location("swiftlint_guard", GUARD_PATH)
  assert spec and spec.loader
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


guard = _load_guard()


def _make_entry(rule: str, file: str, line: int, char: int = 1) -> dict:
  return {
    "violation": {
      "ruleIdentifier": rule,
      "location": {"file": f"file:///repo/Desktop/{file}", "line": line, "character": char},
      "severity": "warning",
    }
  }


class BaselineRatchetTests(unittest.TestCase):

  def test_addition_detected(self):
    """Adding a new violation to the baseline must fail."""
    base = [_make_entry("force_unwrapping", "A.swift", 10)]
    candidate = [_make_entry("force_unwrapping", "A.swift", 10), _make_entry("force_unwrapping", "B.swift", 20)]
    base_keys = {guard._entry_key(e) for e in base}
    candidate_keys = {guard._entry_key(e) for e in candidate}
    additions = candidate_keys - base_keys
    self.assertEqual(len(additions), 1, "must detect the new entry")

  def test_removal_allowed(self):
    """Removing a violation from the baseline must pass."""
    base = [_make_entry("force_unwrapping", "A.swift", 10), _make_entry("force_try", "B.swift", 20)]
    candidate = [_make_entry("force_unwrapping", "A.swift", 10)]
    base_keys = {guard._entry_key(e) for e in base}
    candidate_keys = {guard._entry_key(e) for e in candidate}
    additions = candidate_keys - base_keys
    self.assertEqual(len(additions), 0, "removals are not additions")

  def test_reorder_allowed(self):
    """Reordering entries must not be detected as a change."""
    e1 = _make_entry("force_unwrapping", "A.swift", 10)
    e2 = _make_entry("force_try", "B.swift", 20)
    base_keys = {guard._entry_key(e) for e in [e1, e2]}
    candidate_keys = {guard._entry_key(e) for e in [e2, e1]}
    self.assertEqual(base_keys, candidate_keys, "sets are order-independent")


class DisablePolicyTests(unittest.TestCase):

  def test_blanket_disable_detected(self):
    """A blanket swiftlint:disable (no rule name) must be flagged."""
    line = "// swiftlint:disable"
    self.assertIsNotNone(guard.BLANKET_RE.search(line))
    self.assertIsNone(guard.DISABLE_RE.search(line))

  def test_disable_without_reason_detected(self):
    """swiftlint:disable with a rule but no reason must be flagged."""
    line = "// swiftlint:disable force_unwrapping"
    m = guard.DISABLE_RE.search(line)
    self.assertIsNotNone(m, "should match the disable pattern")
    self.assertIsNone(m.group("reason"), "should have no reason")

  def test_valid_reasoned_disable_accepted(self):
    """swiftlint:disable:this with a named rule and reason must pass."""
    line = "// swiftlint:disable:this force_unwrapping -- proven safe by invariant"
    m = guard.DISABLE_RE.search(line)
    self.assertIsNotNone(m)
    self.assertEqual(m.group("scope"), "this")
    self.assertIn("force_unwrapping", m.group("rules"))
    self.assertEqual(m.group("reason"), "proven safe by invariant")

  def test_multi_rule_without_reason_detected(self):
    """swiftlint:disable with multiple rules but no reason must be flagged."""
    line = "// swiftlint:disable force_unwrapping force_try"
    m = guard.DISABLE_RE.search(line)
    self.assertIsNotNone(m)
    self.assertIsNone(m.group("reason"), "multi-rule without reason should lack a reason group")


class EntryNormalizationTests(unittest.TestCase):

  def test_absolute_path_normalized(self):
    """Absolute file:// URLs must be normalized to relative paths."""
    entry = _make_entry("force_unwrapping", "Sources/Foo.swift", 10)
    key = guard._entry_key(entry)
    self.assertIn("Foo.swift", key[1])
    self.assertNotIn("file://", key[1])

  def test_same_file_different_line_is_different(self):
    """Same file, same rule, different line = different entry."""
    e1 = _make_entry("force_unwrapping", "A.swift", 10)
    e2 = _make_entry("force_unwrapping", "A.swift", 20)
    self.assertNotEqual(guard._entry_key(e1), guard._entry_key(e2))


if __name__ == "__main__":
  unittest.main()
