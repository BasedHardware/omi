"""Unit tests for TOCTOU NotFound guard in folder update and conversation move operations."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

try:
    from google.api_core.exceptions import NotFound as _NotFound
except (ImportError, ModuleNotFoundError):

    class _NotFound(Exception):
        """Stand-in for google.api_core.exceptions.NotFound."""


from database import folders as folders_db


def test_update_folder_deleted_before_update_returns_false():
    """If folder document is deleted concurrently before update, return False rather than throwing NotFound."""
    ref = MagicMock()
    ref.update.side_effect = _NotFound("Folder deleted concurrently")

    col = MagicMock()
    col.document.return_value = ref

    user_ref = MagicMock()
    user_ref.collection.return_value = col

    users_col = MagicMock()
    users_col.document.return_value = user_ref

    db_mock = MagicMock()
    db_mock.collection.return_value = users_col

    with patch.object(folders_db, "db", db_mock):
        result = folders_db.update_folder("user-1", "folder-1", {"name": "Renamed"})
        assert result is False


def test_move_conversation_deleted_before_update_returns_false():
    """If conversation document is deleted concurrently before folder move update, return False."""
    conv_snap = MagicMock()
    conv_snap.exists = True
    conv_snap.to_dict.return_value = {"id": "conv-1", "folder_id": None}

    conv_ref = MagicMock()
    conv_ref.get.return_value = conv_snap
    conv_ref.update.side_effect = _NotFound("Conversation deleted concurrently")

    folder_snap = MagicMock()
    folder_snap.exists = True
    folder_snap.to_dict.return_value = {"id": "folder-1"}

    folder_ref = MagicMock()
    folder_ref.get.return_value = folder_snap

    user_ref = MagicMock()

    def mock_collection(col_name):
        col = MagicMock()
        if col_name == "conversations":
            col.document.return_value = conv_ref
        elif col_name == "folders":
            col.document.return_value = folder_ref
        return col

    user_ref.collection.side_effect = mock_collection

    users_col = MagicMock()
    users_col.document.return_value = user_ref

    db_mock = MagicMock()
    db_mock.collection.return_value = users_col

    with patch.object(folders_db, "db", db_mock):
        result = folders_db.move_conversation_to_folder("user-1", "conv-1", "folder-1")
        assert result is False
