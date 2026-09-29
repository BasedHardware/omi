"""Unit tests for safe folder deserialization in GET /v1/folders.

Verifies that legacy or malformed Firestore folder documents (missing required fields or missing IDs)
are cleanly skipped rather than causing FastAPI ResponseValidationError (HTTP 500) for the user.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

_STUB = (
    "database",
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
    from routers import folders as folders_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


import unittest
from models.folder import UpdateFolderRequest, MoveConversationRequest, BulkMoveConversationsRequest


class TestFoldersSafeDeserialization(unittest.TestCase):
    def test_get_folders_skips_malformed_folder_doc(self):
        """GET /v1/folders must skip malformed docs without raising 500."""
        now = datetime.now(timezone.utc)
        mock_data = [
            {
                "id": "f_valid_1",
                "name": "Work",
                "color": "#3B82F6",
                "icon": "💼",
                "created_at": now,
                "updated_at": now,
                "order": 0,
            },
            {
                "id": "f_corrupt_2",
                # missing required 'name', 'color', 'icon', 'created_at', 'updated_at'
                "description": "Corrupt record",
            },
            {
                # missing required 'id'
                "name": "Missing ID",
                "color": "#8B5CF6",
                "icon": "👥",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "f_valid_3",
                "name": "Personal",
                "color": "#10B981",
                "icon": "👤",
                "created_at": now,
                "updated_at": now,
                "order": 1,
            },
        ]

        with patch.object(folders_mod.folders_db, "get_folders", return_value=mock_data):
            result = folders_mod.get_folders(uid="test_user")

        folder_ids = [f.id if hasattr(f, "id") else f["id"] for f in result]
        self.assertEqual(folder_ids, ["f_valid_1", "f_valid_3"])
        self.assertEqual(len(result), 2)

    def test_get_folders_empty_initializes_system(self):
        """When no folders exist, initialize_system_folders is called and returned safely."""
        now = datetime.now(timezone.utc)
        system_folders = [
            {
                "id": "f_sys_1",
                "name": "Work",
                "color": "#3B82F6",
                "icon": "💼",
                "created_at": now,
                "updated_at": now,
                "order": 0,
            }
        ]
        with patch.object(folders_mod.folders_db, "get_folders", return_value=[]), patch.object(
            folders_mod.folders_db, "initialize_system_folders", return_value=system_folders
        ):
            result = folders_mod.get_folders(uid="test_new_user")

        self.assertEqual([f.id if hasattr(f, "id") else f["id"] for f in result], ["f_sys_1"])

    def test_get_folder_valid(self):
        """GET /v1/folders/{folder_id} returns a valid Folder model when doc is well-formed."""
        now = datetime.now(timezone.utc)
        valid_doc = {
            "id": "f_valid",
            "name": "Work",
            "color": "#3B82F6",
            "icon": "💼",
            "created_at": now,
            "updated_at": now,
            "order": 0,
        }
        with patch.object(folders_mod.folders_db, "get_folder", return_value=valid_doc):
            folder = folders_mod.get_folder(folder_id="f_valid", uid="test_user")

        folder_id = folder["id"] if isinstance(folder, dict) else folder.id
        folder_name = folder["name"] if isinstance(folder, dict) else folder.name
        self.assertEqual(folder_id, "f_valid")
        self.assertEqual(folder_name, "Work")

    def test_get_folder_malformed_returns_404(self):
        """GET /v1/folders/{folder_id} raises 404 when stored folder doc is malformed (missing required fields)."""
        malformed_doc = {
            "id": "f_corrupt",
            # missing required 'name', 'created_at', 'updated_at'
            "description": "Corrupt record",
        }
        with patch.object(folders_mod.folders_db, "get_folder", return_value=malformed_doc):
            with self.assertRaises(HTTPException) as ctx:
                folders_mod.get_folder(folder_id="f_corrupt", uid="test_user")

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Folder not found")

    def test_update_folder_malformed_existing_returns_404(self):
        """PATCH /v1/folders/{folder_id} raises 404 when existing folder doc is malformed."""
        malformed_doc = {
            "id": "f_corrupt",
            "description": "Corrupt record",
        }
        with patch.object(folders_mod.folders_db, "get_folder", return_value=malformed_doc):
            with self.assertRaises(HTTPException) as ctx:
                folders_mod.update_folder(
                    folder_id="f_corrupt",
                    request=UpdateFolderRequest(name="New Name"),
                    uid="test_user",
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Folder not found")

    def test_update_folder_valid(self):
        """PATCH /v1/folders/{folder_id} successfully updates and returns Folder model."""
        now = datetime.now(timezone.utc)
        initial_doc = {
            "id": "f_valid",
            "name": "Old Name",
            "color": "#3B82F6",
            "icon": "💼",
            "created_at": now,
            "updated_at": now,
            "order": 0,
        }
        updated_doc = {
            "id": "f_valid",
            "name": "New Name",
            "color": "#3B82F6",
            "icon": "💼",
            "created_at": now,
            "updated_at": now,
            "order": 0,
        }
        with patch.object(folders_mod.folders_db, "get_folder", side_effect=[initial_doc, updated_doc]), patch.object(
            folders_mod.folders_db, "update_folder", return_value=None
        ):
            folder = folders_mod.update_folder(
                folder_id="f_valid",
                request=UpdateFolderRequest(name="New Name"),
                uid="test_user",
            )

        folder_name = folder["name"] if isinstance(folder, dict) else folder.name
        self.assertEqual(folder_name, "New Name")

    def test_delete_folder_malformed_target_returns_404(self):
        """DELETE /v1/folders/{folder_id} raises 404 if move_to_folder_id references a malformed folder."""
        now = datetime.now(timezone.utc)
        folder_to_delete = {
            "id": "f_del",
            "name": "To Delete",
            "color": "#3B82F6",
            "icon": "💼",
            "created_at": now,
            "updated_at": now,
            "is_system": False,
        }
        malformed_target = {"id": "f_target_corrupt"}
        with patch.object(folders_mod.folders_db, "get_folder", side_effect=[folder_to_delete, malformed_target]):
            with self.assertRaises(HTTPException) as ctx:
                folders_mod.delete_folder(
                    folder_id="f_del",
                    move_to_folder_id="f_target_corrupt",
                    uid="test_user",
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Target folder not found")

    def test_move_conversation_malformed_folder_returns_404(self):
        """PATCH /v1/conversations/{conv_id}/folder raises 404 if destination folder doc is malformed."""
        valid_conv = {"id": "c1", "is_locked": False}
        malformed_folder = {"id": "f_corrupt"}
        with patch.object(folders_mod.conversations_db, "get_conversation", return_value=valid_conv), patch.object(
            folders_mod.folders_db, "get_folder", return_value=malformed_folder
        ):
            with self.assertRaises(HTTPException) as ctx:
                folders_mod.move_conversation_to_folder(
                    conversation_id="c1",
                    request=MoveConversationRequest(folder_id="f_corrupt"),
                    uid="test_user",
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Folder not found")

    def test_bulk_move_malformed_folder_returns_404(self):
        """POST /v1/folders/{folder_id}/conversations/bulk-move raises 404 if target folder doc is malformed."""
        malformed_folder = {"id": "f_corrupt"}
        with patch.object(folders_mod.folders_db, "get_folder", return_value=malformed_folder):
            with self.assertRaises(HTTPException) as ctx:
                folders_mod.bulk_move_conversations(
                    folder_id="f_corrupt",
                    request=BulkMoveConversationsRequest(conversation_ids=["c1", "c2"]),
                    uid="test_user",
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Folder not found")


if __name__ == "__main__":
    unittest.main()
