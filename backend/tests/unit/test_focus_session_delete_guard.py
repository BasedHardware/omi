"""Unit tests for TOCTOU NotFound guard in focus session deletion."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

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


from database import focus_sessions as focus_db


def test_delete_focus_session_missing_returns_false():
    """If document does not exist, return False."""
    client = MagicMock()
    snap = MagicMock()
    snap.exists = False

    ref = MagicMock()
    ref.get.return_value = snap

    col = MagicMock()
    col.document.return_value = ref

    user_ref = MagicMock()
    user_ref.collection.return_value = col

    users_col = MagicMock()
    users_col.document.return_value = user_ref
    client.collection.return_value = users_col

    result = focus_db.delete_focus_session("user-1", "sess-1", client=client)
    assert result is False
    ref.delete.assert_not_called()


def test_delete_focus_session_concurrent_deletion_catches_notfound():
    """If document is deleted concurrently between get and delete, catch NotFound and return False."""
    client = MagicMock()
    snap = MagicMock()
    snap.exists = True

    ref = MagicMock()
    ref.get.return_value = snap
    ref.delete.side_effect = _NotFound("Session deleted concurrently")

    col = MagicMock()
    col.document.return_value = ref

    user_ref = MagicMock()
    user_ref.collection.return_value = col

    users_col = MagicMock()
    users_col.document.return_value = user_ref
    client.collection.return_value = users_col

    result = focus_db.delete_focus_session("user-1", "sess-1", client=client)
    assert result is False
    ref.delete.assert_called_once()


def test_delete_focus_session_success_returns_true():
    """Normal deletion returns True."""
    client = MagicMock()
    snap = MagicMock()
    snap.exists = True

    ref = MagicMock()
    ref.get.return_value = snap
    ref.delete.return_value = None

    col = MagicMock()
    col.document.return_value = ref

    user_ref = MagicMock()
    user_ref.collection.return_value = col

    users_col = MagicMock()
    users_col.document.return_value = user_ref
    client.collection.return_value = users_col

    result = focus_db.delete_focus_session("user-1", "sess-1", client=client)
    assert result is True
    ref.delete.assert_called_once()
