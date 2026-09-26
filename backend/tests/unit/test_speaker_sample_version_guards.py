"""Tests for speaker sample version and timestamp guards preventing TypeError on null or malformed data."""

import ast
from pathlib import Path
from typing import Any, Mapping, Optional
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = BACKEND_DIR / "utils" / "speaker_sample_migration.py"
LISTEN_PATH = BACKEND_DIR / "routers" / "listen" / "speakers.py"
SYNC_PATH = BACKEND_DIR / "utils" / "sync" / "pipeline.py"
IDENTIFICATION_PATH = BACKEND_DIR / "utils" / "speaker_identification.py"


def _extract_get_samples_version():
    """Extract _get_samples_version definition independently of external C/cloud libraries."""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_get_samples_version":
            code = compile(ast.Module(body=[node], type_ignores=[]), filename="<ast>", mode="exec")
            namespace = {"Optional": Optional, "Mapping": Mapping, "Any": Any}
            exec(code, namespace)
            return namespace["_get_samples_version"]
    raise NameError("_get_samples_version not found in speaker_sample_migration.py")


class TestGetSamplesVersionHelper(unittest.TestCase):
    def setUp(self):
        self.get_version = _extract_get_samples_version()

    def test_valid_integer_version(self):
        self.assertEqual(self.get_version({"speech_samples_version": 3}), 3)
        self.assertEqual(self.get_version({"speech_samples_version": 2}), 2)
        self.assertEqual(self.get_version({"speech_samples_version": 1}), 1)

    def test_explicit_none_version_defaults_to_one(self):
        # In Firestore, null fields are deserialized as None.
        # person.get('speech_samples_version', 1) returns None, which crashed version >= 3 with TypeError.
        self.assertEqual(self.get_version({"speech_samples_version": None}), 1)

    def test_missing_version_defaults_to_one(self):
        self.assertEqual(self.get_version({}), 1)
        self.assertEqual(self.get_version({"id": "person-1"}), 1)

    def test_boolean_version_defaults_to_one(self):
        # In Python, isinstance(True, int) is True; verify bool is rejected as invalid schema.
        self.assertEqual(self.get_version({"speech_samples_version": True}), 1)
        self.assertEqual(self.get_version({"speech_samples_version": False}), 1)

    def test_string_or_float_version_defaults_to_one(self):
        self.assertEqual(self.get_version({"speech_samples_version": "3"}), 1)
        self.assertEqual(self.get_version({"speech_samples_version": 3.5}), 1)

    def test_none_or_empty_person(self):
        self.assertEqual(self.get_version(None), 1)
        self.assertEqual(self.get_version({}, default=2), 2)


class TestSpeakerSampleVersionStructuralGuards(unittest.TestCase):
    def test_migration_uses_safe_helper(self):
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("def _get_samples_version", source)
        # Ensure vulnerable pattern is eliminated
        self.assertNotIn("person.get('speech_samples_version', 1) >=", source)
        self.assertNotIn("fresh_person.get('speech_samples_version', 1) >=", source)
        self.assertNotIn("person.get('speech_samples_version', 1) <", source)

    def test_listen_router_guards_version(self):
        source = LISTEN_PATH.read_text(encoding="utf-8")
        self.assertNotIn(
            "bool(person.get('speech_samples')) and (person.get('speech_samples_version', 1) >= 3)",
            source,
            "Raw comparison in listen router must be guarded against NoneType",
        )
        self.assertIn("isinstance(v, int)", source)

    def test_sync_pipeline_guards_version(self):
        source = SYNC_PATH.read_text(encoding="utf-8")
        self.assertNotIn(
            "person.get('speech_samples_version', 1) >= 3",
            source,
            "Raw comparison in sync pipeline must be guarded against NoneType",
        )
        self.assertIn("isinstance(v, int)", source)

    def test_speaker_identification_guards_segment_timestamps(self):
        source = IDENTIFICATION_PATH.read_text(encoding="utf-8")
        self.assertNotIn(
            "s.get('start', 0) < sample_end",
            source,
            "Segment start timestamp comparison must guard against None with or 0.0",
        )
        self.assertIn("(s.get('start') or 0.0) < sample_end", source)
        self.assertIn("(s.get('end') or 0.0) > sample_start", source)


class TestSegmentTimestampFiltering(unittest.TestCase):
    def test_segment_with_none_timestamps_does_not_raise(self):
        sample_start = 5.0
        sample_end = 15.0

        ordered_segments = [
            {"id": "s1", "start": None, "end": 10.0, "speaker_id": 1, "person_id": "p1"},
            {"id": "s2", "start": 6.0, "end": None, "speaker_id": 1, "person_id": "p1"},
            {"id": "s3", "start": 7.0, "end": 12.0, "speaker_id": 1, "person_id": "p1"},
            {"id": "s4", "start": 16.0, "end": 20.0, "speaker_id": 1, "person_id": "p1"},
        ]

        # Must not throw TypeError: '<' not supported between instances of 'NoneType' and 'float'
        contributing = [
            s for s in ordered_segments
            if (s.get('start') or 0.0) < sample_end and (s.get('end') or 0.0) > sample_start
        ]

        # s1 (start None -> 0.0 < 15.0, end 10.0 > 5.0) is included
        # s2 (start 6.0, end None -> 0.0, not > 5.0) is excluded
        # s3 (start 7.0, end 12.0) is included
        # s4 (start 16.0) is excluded
        self.assertEqual(len(contributing), 2)
        self.assertEqual([s["id"] for s in contributing], ["s1", "s3"])


if __name__ == "__main__":
    unittest.main()
