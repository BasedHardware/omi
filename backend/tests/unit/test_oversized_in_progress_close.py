"""An in_progress conversation at Firestore's 1 MiB ceiling is closed, not retried forever.

Prod (2026-09-30..10-04): live-capture rows whose documents sat a few dozen
bytes under the ceiling rejected the finalization binding (it grows the
document) on every listen session, so they stayed ``in_progress`` and invisible
while each reconnect retried them. ``in_progress`` -> ``completed`` is the one
lifecycle write such a document still accepts. These tests pin the
transactional fences and the terminal write; the listen sweep wiring is in
``test_listen_process_pending_shutdown.py``.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import Aborted, InvalidArgument

from database import oversized_conversation_terminal as oversized_terminal_db
from database._client import firestore_failure_reason
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.finalization_failure import FinalizationFailure, classify_finalization_failure
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes

_PATH = 'users/uid-1/conversations/conv-1'
_NOW = datetime.now(timezone.utc)
_QUIET_BEFORE = _NOW - timedelta(hours=1)


class _Snapshot:
    def __init__(self, data: dict | None, update_time: datetime | None) -> None:
        self.exists = data is not None
        self._data = data
        self.update_time = update_time

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Ref:
    path = _PATH

    def __init__(self, snapshot: _Snapshot) -> None:
        self.snapshot = snapshot

    def get(self, transaction=None):
        assert transaction is not None, 'the fences must be read inside the transaction'
        return self.snapshot


class _Transaction:
    def __init__(self) -> None:
        self.updates: list[tuple[object, dict]] = []

    def update(self, ref, data):
        self.updates.append((ref, data))


def _row(*, stored_bytes: int, **overrides) -> dict:
    """A live-capture row whose encrypted transcript blob takes ``stored_bytes``."""
    row = {
        'id': 'conv-1',
        'status': 'in_progress',
        'source': 'omi',
        'started_at': _NOW - timedelta(days=6),
        'finished_at': _NOW - timedelta(days=6),
        'structured': {'title': '', 'overview': ''},
        'transcript_segments_compressed': True,
        # Undecodable on purpose: the terminal must never depend on decrypting it.
        'transcript_segments': os.urandom(stored_bytes),
    }
    row.update(overrides)
    return row


def _at_ceiling(**overrides) -> dict:
    """A row 40 bytes under the ceiling: the ~140-byte finalization binding cannot fit."""
    row = _row(stored_bytes=1, **overrides)
    filler = FIRESTORE_MAX_DOCUMENT_BYTES - 40 - estimate_firestore_document_bytes(row, _PATH)
    return _row(stored_bytes=1 + filler, **overrides)


def _close(data: dict | None, *, update_time: datetime | None = _QUIET_BEFORE - timedelta(days=5)):
    ref = _Ref(_Snapshot(data, update_time))
    transaction = _Transaction()
    outcome = oversized_terminal_db._complete_oversized_in_progress_conversation_txn(
        transaction, ref, _QUIET_BEFORE, 'uid-1'
    )
    return outcome, transaction.updates


def test_row_at_the_ceiling_is_closed_with_a_shrinking_status_only_write():
    row = _at_ceiling()
    assert (
        FIRESTORE_MAX_DOCUMENT_BYTES - 64
        < estimate_firestore_document_bytes(row, _PATH)
        < (FIRESTORE_MAX_DOCUMENT_BYTES)
    )

    outcome, updates = _close(row)

    assert outcome == 'closed'
    assert len(updates) == 1
    # Status only: the transcript and every other field stay exactly as stored, and the
    # optional deterministic title is dropped because it cannot fit.
    assert updates[0][1] == {'status': 'completed'}
    after = {**row, **updates[0][1]}
    assert estimate_firestore_document_bytes(after, _PATH) < estimate_firestore_document_bytes(row, _PATH)


def test_absent_row_is_left_alone():
    assert _close(None) == ('missing', [])


def test_only_in_progress_rows_are_closed():
    for status in ('processing', 'completed', 'failed', 'merging'):
        assert _close(_at_ceiling(status=status)) == ('not_in_progress', [])


def test_discarded_deleted_deferred_or_durably_owned_rows_are_left_alone():
    for fence in (
        {'discarded': True},
        {'deleted': True},
        {'deferred': True},
        {'finalization_job_id': 'job-1'},
    ):
        assert _close(_at_ceiling(**fence)) == ('owned', []), fence


def test_a_row_written_within_the_quiet_window_is_left_alone():
    assert _close(_at_ceiling(), update_time=_QUIET_BEFORE + timedelta(seconds=1)) == ('recent_write', [])
    # No server-owned write clock proves nothing.
    assert _close(_at_ceiling(), update_time=None) == ('recent_write', [])


def test_a_row_that_is_not_near_the_ceiling_keeps_normal_finalization():
    row = _row(stored_bytes=900_000)

    assert _close(row) == ('below_ceiling', [])


def test_lifecycle_owner_delegates_with_the_quiet_window(monkeypatch):
    calls = []

    def fake(uid, conversation_id, *, quiet_for):
        calls.append((uid, conversation_id, quiet_for))
        return 'closed'

    monkeypatch.setattr(oversized_terminal_db, 'complete_oversized_in_progress_conversation', fake)

    outcome = lifecycle_service.close_oversized_in_progress_conversation(
        'uid-1', 'conv-1', quiet_for=timedelta(hours=1)
    )

    assert outcome == 'closed'
    assert calls == [('uid-1', 'conv-1', timedelta(hours=1))]


def test_failure_reason_tokens_are_bounded_and_carry_no_message():
    size = InvalidArgument(
        "Document 'projects/p/databases/(default)/documents/users/uid-1/conversations/conv-1' cannot be "
        'written because its size (1,048,684 bytes) exceeds the maximum allowed size of 1,048,576 bytes.'
    )
    assert firestore_failure_reason(size) == 'document_size_limit'
    assert (
        firestore_failure_reason(InvalidArgument('The referenced transaction has expired or is no longer valid.'))
        == 'expired_transaction'
    )
    assert firestore_failure_reason(ValueError('Failed to commit transaction in 5 attempts.')) == 'contention'
    assert firestore_failure_reason(Aborted('Too much contention on these documents.')) == 'contention'
    assert firestore_failure_reason(FirestoreContentionExhausted('exhausted')) == 'contention'
    assert firestore_failure_reason(InvalidArgument('some other 400')) == 'other'
    assert firestore_failure_reason(ValueError('unrelated')) == 'other'
    assert firestore_failure_reason(RuntimeError('boom')) == 'other'


def test_only_a_rejection_of_the_rows_own_document_is_its_size_limit():
    own = InvalidArgument(
        "Document 'projects/p/databases/(default)/documents/users/uid-1/conversations/conv-1' cannot be "
        'written because its size (1,048,684 bytes) exceeds the maximum allowed size of 1,048,576 bytes.'
    )
    assert classify_finalization_failure(own, 'conv-1') == FinalizationFailure(
        reason='document_size_limit', document='conversation', names_conversation=True
    )
    assert classify_finalization_failure(own, 'conv-1').conversation_at_size_limit
    assert not classify_finalization_failure(own, 'conv-2').conversation_at_size_limit
    contention = classify_finalization_failure(ValueError('Failed to commit transaction in 5 attempts.'), 'conv-1')
    assert contention == FinalizationFailure(reason='contention', document='none', names_conversation=False)
