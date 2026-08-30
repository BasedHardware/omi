#!/usr/bin/env python3
"""Behavioral and mutation tests for the structured-string sink registry."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_structured_string_sinks", SCRIPT_DIR / "check_structured_string_sinks.py"
)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


class StructuredStringSinkRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entries = CHECKER.load_registry(REPOSITORY_ROOT)

    def test_registry_covers_all_three_historical_failure_classes(self) -> None:
        by_id = {entry["id"]: entry for entry in self.entries}
        self.assertEqual(
            set(by_id),
            {
                "deploy-cloudrun-env-vars-v3",
                "llm-gateway-probe-split-argv",
                "llm-gateway-probe-explicit-interpreter",
            },
        )
        self.assertEqual(
            {entry["failure_class"] for entry in self.entries},
            {
                "FC-deploy-input-serialization",
                "FC-workflow-script-input-contract",
                "FC-workflow-executable-assumption",
            },
        )
        evidence = {number for entry in self.entries for number in entry["evidence_prs"]}
        self.assertTrue({9986, 9943, 9945, 9947}.issubset(evidence))

    def test_every_historical_bad_fixture_fails_and_paired_fixture_passes(self) -> None:
        for entry in self.entries:
            with self.subTest(entry=entry["id"], outcome="passing"):
                passing = REPOSITORY_ROOT / entry["fixtures"]["passing"]
                self.assertEqual(CHECKER.check_entry_paths(entry, [passing], REPOSITORY_ROOT), [])
            with self.subTest(entry=entry["id"], outcome="failing"):
                failing = REPOSITORY_ROOT / entry["fixtures"]["failing"]
                violations = CHECKER.check_entry_paths(entry, [failing], REPOSITORY_ROOT)
                self.assertEqual(len(violations), 1)
                self.assertEqual(violations[0].entry_id, entry["id"])
                self.assertIn(str(entry["evidence_prs"][-1]), failing.read_text(encoding="utf-8"))

    def test_checked_in_repository_satisfies_every_registered_grammar(self) -> None:
        self.assertEqual(CHECKER.check_repository(REPOSITORY_ROOT, self.entries), [])

    def test_registered_scope_cannot_silently_match_zero_sinks(self) -> None:
        entry = json.loads(json.dumps(next(entry for entry in self.entries if entry["kind"] == "script-split-argv")))
        entry["command"] = "retired-command-that-does-not-exist.sh"
        with self.assertRaisesRegex(ValueError, "matched files but no sink invocation"):
            CHECKER.check_repository(REPOSITORY_ROOT, [entry])

    def test_even_escape_run_does_not_hide_a_raw_delimiter(self) -> None:
        entry = next(entry for entry in self.entries if entry["kind"] == "action-delimited-map")
        self.assertFalse(CHECKER._contains_unescaped(r"one\,two", ",", "\\"))
        self.assertTrue(CHECKER._contains_unescaped(r"one\\,two", ",", "\\"))

    def test_registry_rejects_bare_allowlist_and_ownerless_dynamic_exemption(self) -> None:
        original = next(entry for entry in self.entries if entry["kind"] == "action-delimited-map")
        fixture_root = REPOSITORY_ROOT
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "entry.json"
            bare = json.loads(json.dumps(original))
            bare["allowlist"] = [".github/workflows/example.yml"]
            with self.assertRaisesRegex(ValueError, "bare allowlist is forbidden"):
                CHECKER.validate_entry(bare, source=source, root=fixture_root)

            ownerless = json.loads(json.dumps(original))
            ownerless["dynamic_values"]["owner"] = ""
            with self.assertRaisesRegex(ValueError, "dynamic_values.owner"):
                CHECKER.validate_entry(ownerless, source=source, root=fixture_root)

    def test_registry_requires_both_fixture_polarities(self) -> None:
        original = json.loads(json.dumps(self.entries[0]))
        original["fixtures"].pop("failing")
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "entry.json"
            with self.assertRaisesRegex(ValueError, "fixtures.failing"):
                CHECKER.validate_entry(original, source=source, root=REPOSITORY_ROOT)


if __name__ == "__main__":
    unittest.main()
