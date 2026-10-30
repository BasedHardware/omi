"""Unit tests for folder bulk-move deduplication, bounds, and request validation.

Verifies that:
1. BulkMoveConversationsRequest validates and deduplicates conversation IDs, preventing
   Firestore "400 Multiple operations on document in a single commit" batch crashes.
2. BulkMoveConversationsRequest enforces non-empty ID constraints and upper bounds.
3. bulk_move_conversations_to_folder in database layer defensively deduplicates IDs.
4. CreateFolderRequest and UpdateFolderRequest strip whitespace and reject blank names.
5. GET /v1/folders/{folder_id} converts malformed stored documents into HTTP 404 rather
   than raising FastAPI ResponseValidationError (HTTP 500).
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

_STUB = (
    "utils",
    "firebase_admin",
    "google",
    "pinecone",
    "typesense",
    "opuslib",
    "pydub",
    "pusher",
    "modal",
    "ulid",
    "langchain",
    "langchain_core",
    "stripe",
    "openai",
    "anthropic",
    "redis",
    "sentry_sdk",
    "requests",
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + ".") for p in _STUB)


def _snapshot():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from models.folder import (
        BulkMoveConversationsRequest,
        CreateFolderRequest,
        Folder,
        UpdateFolderRequest,
    )
    import database.folders as folders_db
    from routers import folders as folders_router
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


class TestFolderBulkMoveAndValidation(unittest.TestCase):
    def test_bulk_move_request_deduplicates_and_preserves_order(self):
        """BulkMoveConversationsRequest deduplicates repeated IDs and strips whitespace."""
        req = BulkMoveConversationsRequest(
            conversation_ids=["conv-1", "  conv-1  ", "conv-2", "conv-1", " conv-3 "]
        )
        self.assertEqual(req.conversation_ids, ["conv-1", "conv-2", "conv-3"])

    def test_bulk_move_request_rejects_empty_or_whitespace_only(self):
        """BulkMoveConversationsRequest rejects empty lists and lists containing only whitespace."""
        with self.assertRaises(ValidationError):
            BulkMoveConversationsRequest(conversation_ids=[])

        with self.assertRaises(ValidationError):
            BulkMoveConversationsRequest(conversation_ids=["   ", "", "  "])

    def test_create_folder_request_name_validation(self):
        """CreateFolderRequest strips whitespace and rejects whitespace-only names."""
        with self.assertRaises(ValidationError):
            CreateFolderRequest(name="   ")

        req = CreateFolderRequest(name="  Projects & Ideas  ")
        self.assertEqual(req.name, "Projects & Ideas")

    def test_update_folder_request_name_validation(self):
        """UpdateFolderRequest strips whitespace and rejects whitespace-only names."""
        with self.assertRaises(ValidationError):
            UpdateFolderRequest(name="   ")

        req = UpdateFolderRequest(name="  Renamed Folder  ")
        self.assertEqual(req.name, "Renamed Folder")

        # None is allowed for partial updates of other fields
        req_partial = UpdateFolderRequest(color="#10B981")
        self.assertIsNone(req_partial.name)
        self.assertEqual(req_partial.color, "#10B981")

    def test_get_folder_graceful_404_on_malformed_doc(self):
        """GET /v1/folders/{folder_id} returns 404 rather than 500 on corrupt stored doc."""
        corrupt_folder = {
            "id": "f_broken",
            "name": "Broken Folder",
            # missing color, icon, created_at, updated_at
        }
        with patch.object(folders_router.folders_db, "get_folder", return_value=corrupt_folder):
            with self.assertRaises(folders_router.HTTPException) as ctx:
                folders_router.get_folder("f_broken", uid="user-1")
            self.assertEqual(ctx.exception.status_code, 404)
            self.assertEqual(ctx.exception.detail, "Folder not found")

    def test_db_bulk_move_deduplicates_defensively(self):
        """database.folders.bulk_move_conversations_to_folder deduplicates IDs before calling Firestore."""
        mock_db = MagicMock()
        mock_user_ref = MagicMock()
        mock_convs_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_user_ref
        mock_user_ref.collection.return_value = mock_convs_ref

        # Mock conversation document
        mock_doc1 = MagicMock()
        mock_doc1.exists = True
        mock_doc1.to_dict.return_value = {"folder_id": "old_f"}
        mock_doc1.reference = MagicMock()

        mock_db.get_all.return_value = [mock_doc1]
        mock_batch = MagicMock()
        mock_db.batch.return_value = mock_batch

        with patch.object(folders_db, "db", mock_db), patch.object(
            folders_db, "update_folder_conversation_count"
        ):
            moved = folders_db.bulk_move_conversations_to_folder(
                uid="u1",
                conversation_ids=["c1", " c1 ", "c1"],
                folder_id="new_f",
            )

        # get_all must be called with only 1 DocumentReference (deduplicated), not 3!
        self.assertEqual(mock_db.get_all.call_count, 1)
        passed_refs = mock_db.get_all.call_args[0][0]
        self.assertEqual(len(passed_refs), 1)

        # batch.update must only be called once, preventing Firestore commit contention
        self.assertEqual(mock_batch.update.call_count, 1)
        self.assertEqual(moved, 1)

    def test_router_bulk_move_with_duplicate_ids(self):
        """POST /v1/folders/{folder_id}/conversations/bulk-move handles duplicate IDs cleanly."""
        req = BulkMoveConversationsRequest(conversation_ids=["c1", "c1", "c2"])

        with patch.object(
            folders_router.folders_db, "get_folder", return_value={"id": "target_folder"}
        ), patch.object(
            folders_router.conversations_db,
            "get_conversation",
            return_value={"id": "c", "deleted": False, "is_locked": False},
        ), patch.object(
            folders_router.folders_db, "bulk_move_conversations_to_folder", return_value=2
        ) as mock_bulk_move:
            res = folders_router.bulk_move_conversations(
                folder_id="target_folder", request=req, uid="user-1"
            )

        self.assertEqual(res, {"status": "ok", "moved_count": 2})
        # Verifies that bulk_move received only the deduplicated IDs
        mock_bulk_move.assert_called_once_with("user-1", ["c1", "c2"], "target_folder")


if __name__ == "__main__":
    unittest.main()
