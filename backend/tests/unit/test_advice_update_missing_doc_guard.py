"""update_advice must return None (404) when the advice is deleted mid-update, not crash with a 500.

PATCH /v1/advice/{advice_id} -> update_advice checks the document exists, applies the update, then
re-reads it to return the fresh value. Two concurrent-deletion windows turned that into a 500:
  1. Deleted between the existence check and ref.update(...) -> Firestore update() raises NotFound.
  2. Deleted between the update and the re-read -> the re-read finds no document.
The router treats a None return as a 404, so both races must yield 404, not an unhandled 500.
These cover the pure database-function behavior; the success path returns the parsed ``Advice``
model through the same read boundary as the feed, with the Firestore document id authoritative.

Test isolation: database.advice imports cleanly (the Firestore client is lazy), so the tests
import the real module and patch only ``_user_col`` — no sys.modules mutation, no stubs, no
services. (The previous harness stubbed google/database leaves at module scope and never
restored them, which leaked fakes process-wide and broke real imports in later test files.)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from google.api_core.exceptions import NotFound

from database import advice as advice_db


def _snap(exists, data=None, doc_id='adv1'):
    snap = MagicMock()
    snap.exists = exists
    snap.id = doc_id
    snap.to_dict.return_value = data
    return snap


def _valid_payload(**overrides):
    payload = {
        'content': 'Review your weekly focus report',
        'category': 'focus',
        'confidence': 0.8,
        'created_at': datetime(2026, 9, 30, tzinfo=timezone.utc),
        'updated_at': datetime(2026, 9, 30, tzinfo=timezone.utc),
        'is_read': False,
        'is_dismissed': False,
    }
    payload.update(overrides)
    return payload


def _wire(get_results, update_exc=None):
    """A mocked advice collection whose document().get() yields the given snapshots in order."""
    ref = MagicMock()
    ref.get.side_effect = list(get_results)
    if update_exc is not None:
        ref.update.side_effect = update_exc
    col = MagicMock()
    col.document.return_value = ref
    return col, ref


def test_missing_advice_returns_none():
    # The existence check: a UID/advice_id with no document returns None (404), no update.
    col, ref = _wire([_snap(False)])
    with patch.object(advice_db, '_user_col', return_value=col):
        assert advice_db.update_advice('u', 'adv1', is_read=True) is None
    ref.update.assert_not_called()


def test_deleted_before_update_returns_none():
    # Deleted between the existence check and the update: Firestore update() raises NotFound, which
    # must become a None return (404), not a propagated 500.
    col, ref = _wire([_snap(True)], update_exc=NotFound('deleted mid-update'))
    with patch.object(advice_db, '_user_col', return_value=col):
        assert advice_db.update_advice('u', 'adv1', is_read=True) is None


def test_deleted_after_update_returns_none():
    # Deleted between the update and the re-read: a missing document must become a None return
    # instead of a TypeError on the old result['id'] indexing.
    col, ref = _wire([_snap(True), _snap(False, None)])
    with patch.object(advice_db, '_user_col', return_value=col):
        assert advice_db.update_advice('u', 'adv1', is_dismissed=True) is None


def test_happy_path_returns_parsed_advice_model():
    # The success path parses through the same read boundary as the feed: an Advice model whose
    # id is the Firestore document id (authoritative), not merely the stored field.
    col, ref = _wire([_snap(True, _valid_payload()), _snap(True, _valid_payload(is_read=True))])
    with patch.object(advice_db, '_user_col', return_value=col):
        result = advice_db.update_advice('u', 'adv1', is_read=True)
    assert result is not None
    assert result.id == 'adv1'
    assert result.content == 'Review your weekly focus report'
    assert result.is_read is True
