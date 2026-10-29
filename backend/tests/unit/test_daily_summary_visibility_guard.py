"""Unit tests for TOCTOU NotFound guard in daily summaries visibility and delivery completion."""

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


from database import daily_summaries as daily_db


def test_set_daily_summary_visibility_missing_returns_false():
    """If daily summary document is deleted concurrently, return False rather than throwing NotFound."""
    client = MagicMock()
    ref = MagicMock()
    ref.update.side_effect = _NotFound("Document deleted concurrently")

    summary_col = MagicMock()
    summary_col.document.return_value = ref

    user_ref = MagicMock()
    user_ref.collection.return_value = summary_col

    users_col = MagicMock()
    users_col.document.return_value = user_ref
    client.collection.return_value = users_col

    result = daily_db.set_daily_summary_visibility("user-1", "summary-1", "shared", firestore_client=client)
    assert result is False
    ref.update.assert_called_once_with({"visibility": "shared"})


def test_set_daily_summary_visibility_success_returns_true():
    """Normal visibility update returns True."""
    client = MagicMock()
    ref = MagicMock()
    ref.update.return_value = None

    summary_col = MagicMock()
    summary_col.document.return_value = ref

    user_ref = MagicMock()
    user_ref.collection.return_value = summary_col

    users_col = MagicMock()
    users_col.document.return_value = user_ref
    client.collection.return_value = users_col

    result = daily_db.set_daily_summary_visibility("user-1", "summary-1", "private", firestore_client=client)
    assert result is True
    ref.update.assert_called_once_with({"visibility": "private"})


def test_mark_daily_summary_delivery_completed_missing_returns_false():
    """If delivery completed is marked after summary is deleted, catch NotFound and return False."""
    client = MagicMock()
    ref = MagicMock()
    ref.update.side_effect = _NotFound("Document deleted concurrently")

    summary_col = MagicMock()
    summary_col.document.return_value = ref

    user_ref = MagicMock()
    user_ref.collection.return_value = summary_col

    users_col = MagicMock()
    users_col.document.return_value = user_ref
    client.collection.return_value = users_col

    result = daily_db.mark_daily_summary_delivery_completed("user-1", "summary-1", firestore_client=client)
    assert result is False
    ref.update.assert_called_once_with({"notification_delivery_completed": True})


def test_mark_daily_summary_delivery_completed_success_returns_true():
    """Normal delivery completion returns True."""
    client = MagicMock()
    ref = MagicMock()
    ref.update.return_value = None

    summary_col = MagicMock()
    summary_col.document.return_value = ref

    user_ref = MagicMock()
    user_ref.collection.return_value = summary_col

    users_col = MagicMock()
    users_col.document.return_value = user_ref
    client.collection.return_value = users_col

    result = daily_db.mark_daily_summary_delivery_completed("user-1", "summary-1", firestore_client=client)
    assert result is True
    ref.update.assert_called_once_with({"notification_delivery_completed": True})
