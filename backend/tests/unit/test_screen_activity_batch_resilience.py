"""Unit tests for screen activity batch resilience, deduplication, and input guards.

Verifies:
- Document deduplication within batch commits to prevent Firestore:
  '400 Multiple operations on document in a single commit'
- Bounded 499-op commit chunking to stay strictly below the 500 Firestore ceiling
- Input validation on empty/whitespace uid across readers and mutators
- Safe handling of missing or malformed document IDs
"""

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


# Preflight stubs for bare python3 hygiene runner environments without dependencies
for p in ["google", "google.api_core", "google.cloud", "models"]:
    _pkg(p)

_exc = _mod("google.api_core.exceptions")
if not hasattr(_exc, "InvalidArgument"):
    _exc.InvalidArgument = type("InvalidArgument", (Exception,), {})

_fs = _mod("google.cloud.firestore")
if not hasattr(_fs, "Query"):
    _fs.Query = MagicMock()
if not hasattr(_fs, "FieldFilter"):
    _fs.FieldFilter = MagicMock()

_sa = _mod("models.screen_activity")
if not hasattr(_sa, "ScreenActivityCoverage"):

    class _FakeScreenActivityCoverage:
        def __init__(self, **kwargs):
            self._data = kwargs

        def model_dump(self):
            return self._data

    _sa.ScreenActivityCoverage = _FakeScreenActivityCoverage

from database import screen_activity


class ScreenActivityBatchResilienceTests(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.orig_db = screen_activity.db
        screen_activity.db = self.mock_db

    def tearDown(self):
        screen_activity.db = self.orig_db

    def test_upsert_screen_activity_empty_uid_raises_value_error(self):
        with self.assertRaises(ValueError):
            screen_activity.upsert_screen_activity("", [{"id": "1", "timestamp": "2026-09-27T12:00:00Z"}])

        with self.assertRaises(ValueError):
            screen_activity.upsert_screen_activity("   ", [{"id": "1", "timestamp": "2026-09-27T12:00:00Z"}])

    def test_upsert_screen_activity_empty_rows_returns_zero(self):
        result = screen_activity.upsert_screen_activity("user-1", [])
        self.assertEqual(result, 0)
        self.mock_db.collection.assert_not_called()

    def test_upsert_screen_activity_deduplicates_duplicate_document_ids(self):
        """Multiple rows with identical storageId/id must be deduplicated to prevent
        Firestore 'Multiple operations on document in a single commit' exceptions."""
        mock_batch = MagicMock()
        self.mock_db.batch.return_value = mock_batch
        mock_collection = MagicMock()
        mock_doc = MagicMock()
        mock_collection.document.return_value = mock_doc
        self.mock_db.collection.return_value.document.return_value.collection.return_value = mock_collection

        # 3 rows, but two share the same id "shot-1" with different window titles
        rows = [
            {"storageId": "shot-1", "timestamp": "2026-09-27T12:00:00Z", "windowTitle": "Old Title"},
            {"storageId": "shot-2", "timestamp": "2026-09-27T12:00:01Z", "windowTitle": "Unique"},
            {"storageId": "shot-1", "timestamp": "2026-09-27T12:00:02Z", "windowTitle": "New Title"},
        ]

        written = screen_activity.upsert_screen_activity("user-1", rows)

        self.assertEqual(written, 2)
        self.assertEqual(mock_batch.set.call_count, 2)
        mock_batch.commit.assert_called_once()

        # The latest row ("New Title") should be the one preserved
        called_doc_data = [call.args[1] for call in mock_batch.set.call_args_list]
        shot_1_data = next(d for d in called_doc_data if d["localScreenshotId"] == "shot-1")
        self.assertEqual(shot_1_data["windowTitle"], "New Title")
        self.assertEqual(shot_1_data["timestamp"], "2026-09-27T12:00:02Z")

    def test_upsert_screen_activity_chunks_at_499_operations(self):
        """Commits must chunk at 499 operations to avoid exceeding the Firestore 500-op limit."""
        batches = []

        def make_batch():
            b = MagicMock()
            batches.append(b)
            return b

        self.mock_db.batch.side_effect = make_batch
        mock_collection = MagicMock()
        self.mock_db.collection.return_value.document.return_value.collection.return_value = mock_collection

        # 1000 distinct items should produce 3 batches: 499, 499, and 2
        rows = [{"id": f"shot-{i}", "timestamp": "2026-09-27T12:00:00Z"} for i in range(1000)]

        written = screen_activity.upsert_screen_activity("user-1", rows)

        self.assertEqual(written, 1000)
        self.assertEqual(len(batches), 3)
        self.assertEqual(batches[0].set.call_count, 499)
        batches[0].commit.assert_called_once()
        self.assertEqual(batches[1].set.call_count, 499)
        batches[1].commit.assert_called_once()
        self.assertEqual(batches[2].set.call_count, 2)
        batches[2].commit.assert_called_once()

    def test_upsert_screen_activity_skips_malformed_and_invalid_ids(self):
        mock_batch = MagicMock()
        self.mock_db.batch.return_value = mock_batch

        rows = [
            "not-a-dict",
            {"no_id": True},
            {"id": "   "},
            {"id": "invalid/slash/id"},
            {"id": "valid-1", "timestamp": "2026-09-27T12:00:00Z"},
        ]

        written = screen_activity.upsert_screen_activity("user-1", rows)
        self.assertEqual(written, 1)
        self.assertEqual(mock_batch.set.call_count, 1)
        mock_batch.commit.assert_called_once()

    def test_get_screen_activity_ids_empty_uid_returns_empty_list(self):
        self.assertEqual(screen_activity.get_screen_activity_ids(""), [])
        self.assertEqual(screen_activity.get_screen_activity_ids("   "), [])
        self.mock_db.collection.assert_not_called()

    def test_get_screen_activity_empty_uid_returns_empty_list(self):
        self.assertEqual(screen_activity.get_screen_activity(""), [])
        self.assertEqual(screen_activity.get_screen_activity("   "), [])
        self.mock_db.collection.assert_not_called()

    def test_get_screen_activity_page_empty_uid_returns_empty_tuple(self):
        rows, has_more = screen_activity.get_screen_activity_page("")
        self.assertEqual(rows, [])
        self.assertFalse(has_more)
        self.mock_db.collection.assert_not_called()

    def test_get_screen_activity_summary_empty_uid_returns_empty_summary(self):
        summary = screen_activity.get_screen_activity_summary("")
        self.assertEqual(summary["apps"], {})
        self.assertEqual(summary["total_screenshots"], 0)
        self.assertEqual(summary["coverage"]["row_limit"], 5000)
        self.assertFalse(summary["coverage"]["truncated"])
        self.mock_db.collection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
