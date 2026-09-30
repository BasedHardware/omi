"""Every row the finalization dead-letter keeps visible carries a useful title.

Row states (David's rule: a listed row always carries something useful, and a
"Summary failed · Retry" affordance appears only when retrying can succeed):

* transient failure (``final_attempt_failed`` / ``processing_failed``) with
  transcript or photos -> deterministic title + ``summary_retryable=True``
* ``recovery_structure_unavailable`` with a transcript -> deterministic title only
* no transcript and no photos -> deterministic time title, no retry state
* an existing generated or user title -> untouched, no retry state
"""

from __future__ import annotations

import json
import os
import zlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import conversation_finalization_jobs as jobs
from models.conversation import Conversation
from utils import encryption

_UID = 'uid-1'
_STARTED_AT = datetime(2026, 9, 30, 22, 14, tzinfo=timezone.utc)
_NOW = datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc)


class _Photos:
    def __init__(self, has_photo: bool):
        self.has_photo = has_photo
        self.reads = 0

    def limit(self, count: int):
        assert count == 1
        return self

    def stream(self, transaction=None):
        assert transaction is not None, 'photo probe must read inside the transaction'
        self.reads += 1
        return iter([SimpleNamespace()] if self.has_photo else [])


class _Ref:
    def __init__(self, doc_id: str, data: dict | None, *, has_child_photo: bool = False):
        self.id = doc_id
        self.data = data
        self.photos = _Photos(has_child_photo)

    def get(self, transaction=None):
        del transaction
        return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

    def collection(self, name: str):
        assert name == 'photos'
        return self.photos


class _Transaction:
    def __init__(self):
        self.updates: list[tuple[_Ref, dict]] = []

    def update(self, ref, data):
        self.updates.append((ref, data))


def _job() -> _Ref:
    return _Ref(
        'job-1',
        {
            'status': 'leased',
            'uid': _UID,
            'conversation_id': 'conversation-1',
            'finalization_revision': 3,
            'dispatch_generation': 3,
            'lease_epoch': 1,
        },
    )


def _conversation(extra: dict | None = None, *, has_child_photo: bool = False) -> _Ref:
    return _Ref(
        'conversation-1',
        {
            'status': 'processing',
            'discarded': False,
            'finalization_job_id': 'job-1',
            'finalization_revision': 3,
            'started_at': _STARTED_AT,
            'structured': {'title': '', 'overview': '', 'category': 'other'},
            **(extra or {}),
        },
        has_child_photo=has_child_photo,
    )


def _dead_letter(conversation: _Ref, failure_code: str = 'final_attempt_failed', *, time_zone=None) -> dict:
    transaction = _Transaction()
    zone_calls: list[str] = []

    def zone_for(uid: str):
        zone_calls.append(uid)
        return time_zone

    assert jobs._mark_finalization_dead_letter_txn(
        transaction,
        _job(),
        3,
        1,
        5,
        _NOW,
        lambda uid, conversation_id: conversation,
        None,
        failure_code,
        zone_for,
    )
    conversation_writes = [patch for ref, patch in transaction.updates if ref is conversation]
    assert len(conversation_writes) == 1
    patch = conversation_writes[0]
    patch['_zone_calls'] = zone_calls
    return patch


def _segments(*texts: str) -> list[dict]:
    return [{'text': text, 'speaker': 'SPEAKER_00', 'is_user': False, 'start': 0, 'end': 1} for text in texts]


@pytest.mark.parametrize('failure_code', ['final_attempt_failed', 'processing_failed'])
def test_transient_failure_with_transcript_is_titled_and_retryable(failure_code):
    conversation = _conversation(
        {'transcript_segments': _segments('', 'We picked the venue for Friday. Then lunch.', 'More talk.')}
    )

    patch = _dead_letter(conversation, failure_code)

    assert patch['status'] == 'completed'
    assert patch['discarded'] is False
    assert patch['finalization_status'] == 'dead_letter'
    # Only the title changes; the rest of the stored structured map survives.
    assert patch['structured'] == {'title': 'We picked the venue for Friday.', 'overview': '', 'category': 'other'}
    assert patch['summary_retryable'] is True
    assert patch['_zone_calls'] == []  # a transcript title needs no zone lookup


def test_model_found_nothing_to_summarize_gets_a_title_but_no_retry_state():
    conversation = _conversation({'transcript_segments': _segments('Okay so the plan is fine.')})

    patch = _dead_letter(conversation, 'recovery_structure_unavailable')

    assert patch['structured']['title'] == 'Okay so the plan is fine.'
    assert 'summary_retryable' not in patch


def test_missing_structured_is_created_with_the_deterministic_title():
    conversation = _conversation({'transcript_segments': _segments('Hello there')})
    del conversation.data['structured']

    patch = _dead_letter(conversation)

    assert patch['structured'] == {'title': 'Hello there', 'overview': ''}


def test_enhanced_encrypted_compressed_transcript_is_decoded_for_the_title():
    compressed_hex = zlib.compress(json.dumps(_segments('Encrypted words matter here. Tail.')).encode()).hex()
    conversation = _conversation(
        {
            'data_protection_level': 'enhanced',
            'transcript_segments_compressed': True,
            'transcript_segments': encryption.encrypt(compressed_hex, _UID),
        }
    )

    patch = _dead_letter(conversation)

    assert patch['structured']['title'] == 'Encrypted words matter here.'
    assert patch['summary_retryable'] is True
    # The stored transcript blob is never rewritten by the terminal.
    assert 'transcript_segments' not in patch


def test_standard_compressed_transcript_is_decoded_for_the_title():
    conversation = _conversation(
        {
            'transcript_segments_compressed': True,
            'transcript_segments': zlib.compress(json.dumps(_segments('Compressed bytes too.')).encode()),
        }
    )

    assert _dead_letter(conversation)['structured']['title'] == 'Compressed bytes too.'


def test_undecodable_transcript_degrades_to_the_time_title_without_raising():
    conversation = _conversation(
        {
            'data_protection_level': 'enhanced',
            'transcript_segments_compressed': True,
            'transcript_segments': 'not-a-real-ciphertext',
        }
    )

    patch = _dead_letter(conversation, time_zone='America/Los_Angeles')

    assert patch['status'] == 'completed'
    assert patch['structured']['title'] == 'Recording · 3:14 PM'
    # Nothing readable to summarize: no retry affordance.
    assert 'summary_retryable' not in patch


def test_photo_only_transient_failure_uses_the_user_zone_time_title_and_is_retryable():
    conversation = _conversation({'transcript_segments': []}, has_child_photo=True)

    patch = _dead_letter(conversation, time_zone='America/Los_Angeles')

    assert patch['structured']['title'] == 'Recording · 3:14 PM'
    assert patch['_zone_calls'] == [_UID]
    assert patch['summary_retryable'] is True
    assert conversation.photos.reads == 1


def test_photo_marker_counts_without_a_child_read():
    conversation = _conversation({'has_photos': True})

    patch = _dead_letter(conversation)

    assert patch['summary_retryable'] is True
    assert conversation.photos.reads == 0


def test_no_transcript_and_no_photos_gets_a_title_but_no_retry_state():
    conversation = _conversation({'transcript_segments': _segments('   ')})

    patch = _dead_letter(conversation)

    assert patch['structured']['title'] == 'Recording · 10:14 PM'  # UTC when no zone is known
    assert 'summary_retryable' not in patch


def test_existing_generated_title_is_untouched_and_not_marked_failed():
    conversation = _conversation(
        {
            'structured': {'title': 'Venue planning', 'overview': 'Picked a venue.'},
            'transcript_segments': _segments('We picked the venue.'),
        }
    )

    patch = _dead_letter(conversation)

    assert 'structured' not in patch
    assert 'summary_retryable' not in patch


def test_user_title_is_never_overwritten_and_not_marked_failed():
    conversation = _conversation({'user_title': 'My name for it', 'transcript_segments': _segments('Some words.')})

    patch = _dead_letter(conversation)

    assert 'structured' not in patch
    assert 'summary_retryable' not in patch


def test_unbound_or_discarded_rows_are_not_touched():
    discarded = _conversation({'discarded': True, 'transcript_segments': _segments('x')})
    transaction = _Transaction()
    assert jobs._mark_finalization_dead_letter_txn(
        transaction, _job(), 3, 1, 5, _NOW, lambda uid, conversation_id: discarded, None, 'final_attempt_failed'
    )
    assert [ref for ref, _patch in transaction.updates if ref is discarded] == []


def test_titled_dead_letter_row_is_a_valid_api_conversation():
    conversation = _conversation({'transcript_segments': _segments('Plan the offsite.')})
    patch = _dead_letter(conversation)
    patch.pop('_zone_calls')
    row = Conversation.model_validate(
        {
            'id': 'conversation-1',
            'created_at': _NOW,
            'finished_at': _NOW,
            **conversation.data,
            **patch,
        }
    )
    assert row.structured.title == 'Plan the offsite.'
    assert row.summary_retryable is True
    assert row.processing_state is None


def test_wrapper_resolves_the_zone_with_a_plain_non_transactional_read():
    user = SimpleNamespace(exists=True, to_dict=lambda: {'time_zone': 'Europe/Paris'})
    reads: list[str] = []

    class _Users:
        def document(self, uid):
            reads.append(uid)
            return SimpleNamespace(get=lambda: user)

    client = SimpleNamespace(collection=lambda name: _Users() if name == 'users' else None)
    assert jobs._user_time_zone(client, _UID) == 'Europe/Paris'
    assert reads == [_UID]

    def boom():
        raise RuntimeError('firestore unavailable')

    failing = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda uid: SimpleNamespace(get=boom)))
    assert jobs._user_time_zone(failing, _UID) is None
