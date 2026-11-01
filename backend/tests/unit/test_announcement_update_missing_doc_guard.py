"""update_announcement must return None (404) when the announcement is deleted mid-update, not crash with a 500.

PUT /v1/announcements/{announcement_id} -> update_announcement applies the update, then re-reads the
document to return the fresh Announcement. Two concurrent-deletion windows turned that into a 500:
  1. Deleted between the existence check and doc_ref.update(...) -> Firestore update() raises NotFound.
  2. Deleted between the update and the re-read -> doc_ref.get().exists is False / to_dict() is None.
The router treats a None return as a 404, so both races should yield 404, not an unhandled 500.
"""

import importlib.util
import os
import sys
import types
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


from database import announcements


def _snap(exists, data=None, doc_id="ann-1"):
    snap = MagicMock()
    snap.exists = exists
    snap.id = doc_id
    snap.to_dict.return_value = data
    return snap


def _wire(get_results, update_exc=None):
    ref = MagicMock()
    ref.get.side_effect = list(get_results)
    if update_exc is not None:
        ref.update.side_effect = update_exc
    col = MagicMock()
    col.document.return_value = ref
    db_mock = MagicMock()
    db_mock.collection.return_value = col
    return db_mock, ref


def test_deleted_before_update_returns_none():
    db_mock, _ = _wire(
        [_snap(True, {"id": "ann-1"})],
        update_exc=_NotFound("Document deleted concurrently"),
    )
    with patch.object(announcements, "db", db_mock):
        assert announcements.update_announcement("ann-1", {"active": False}) is None


def test_deleted_after_update_returns_none():
    db_mock, _ = _wire([_snap(True, {"id": "ann-1"}), _snap(False, None)])
    with patch.object(announcements, "db", db_mock):
        assert announcements.update_announcement("ann-1", {"active": False}) is None
