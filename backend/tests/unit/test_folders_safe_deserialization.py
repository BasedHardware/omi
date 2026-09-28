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


def test_get_folders_skips_malformed_folder_doc():
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

    folder_ids = [f.id for f in result]
    assert folder_ids == ["f_valid_1", "f_valid_3"]
    assert len(result) == 2


def test_get_folders_empty_initializes_system():
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

    assert [f.id for f in result] == ["f_sys_1"]


if __name__ == "__main__":
    test_get_folders_skips_malformed_folder_doc()
    test_get_folders_empty_initializes_system()
    print("All folder safe deserialization tests passed!")
