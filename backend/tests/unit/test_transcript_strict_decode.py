"""Transactional binding must not treat an unreadable transcript as empty.

The permissive read decoder maps an undecryptable enhanced blob to ``[]``.
``transcript_sha256_for_binding([])`` is a public constant. Binding is an
authorization decision, not a render path: if the snapshot cannot be decoded,
the projection is dropped and the conversation still finalizes.

A successfully decoded empty list is a real transcript. It still binds to the
empty-transcript digest — we observed emptiness, we did not invent it.

Red-proofs (one-line mutation that would make the named assertion pass wrongly):
- decode the transactional snapshot through ``_prepare_conversation_for_read``
  instead of ``_decode_transcript_segments_strict`` (corrupted blob becomes
  ``[]`` and the empty-transcript digest binds)
- catch decode failure and still hash ``[]`` (same skeleton-key)
- let a decode exception propagate out of ``claim_conversation_status`` /
  ``bind_client_processing`` (conversation is lost / 500)
- bind through ``transcript_sha256`` instead of ``transcript_sha256_for_binding``
  after the strict decode (legacy padded identity matches and still renders
  Speaker 0)
"""

from __future__ import annotations

import json
import logging
import zlib
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from database import conversations as conversations_db
from models.conversation_enums import ConversationStatus
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations.transcript_hash import transcript_sha256, transcript_sha256_for_binding

_UID = 's4-strict-decode-uid'
_CONV_ID = 's4-strict-decode-conv'
_CONV_PATH = ('users', _UID, 'conversations', _CONV_ID)
_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
EMPTY_DIGEST = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
CANARY = 'UNIQUE_STRICT_DECODE_CANARY_xyzzy_not_in_logs'
_SEGMENT_TEXT = 'Hello from the desktop capture'


def _spoken_segments() -> List[Dict[str, Any]]:
    return [
        {
            'id': 's1',
            'text': _SEGMENT_TEXT,
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': True,
            'person_id': '',
            'start': 0.0,
            'end': 1.0,
        }
    ]


def _projection(digest: str) -> Dict[str, Any]:
    return {
        'schema_version': 1,
        'transcript_sha256': digest,
        'structure': {'title': CANARY, 'overview': '', 'category': 'other'},
        'action_items': [],
        'provenance': {
            'model_id': 'local-test-model',
            'runtime': 'mlx',
            'device_class': 'apple_silicon',
            'generated_at': '2026-09-02T12:00:00+00:00',
        },
    }


def _mutation(digest: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {'client_processing': _projection(digest)}
    payload.update(extra)
    return payload


def _encode(segments: List[Dict[str, Any]], *, level: str) -> Dict[str, Any]:
    return conversations_db.encode_conversation_for_write(_UID, {'transcript_segments': segments}, level)


def _snapshot(
    encoded: Dict[str, Any], *, level: str, status: str = ConversationStatus.in_progress.value
) -> Dict[str, Any]:
    return {
        'data_protection_level': level,
        'discarded': False,
        'status': status,
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
        **encoded,
    }


def _corrupt_enhanced_blob(blob: str) -> str:
    assert isinstance(blob, str) and len(blob) >= 4
    tail = 'AAAA' if blob[-4:] != 'AAAA' else 'BBBB'
    return blob[:-4] + tail


def _undecryptable_enhanced_snapshot() -> Dict[str, Any]:
    encoded = _encode(_spoken_segments(), level='enhanced')
    encoded['transcript_segments'] = _corrupt_enhanced_blob(encoded['transcript_segments'])
    return _snapshot(encoded, level='enhanced')


def _install_strict_conversation_db(monkeypatch: pytest.MonkeyPatch, snapshot: Dict[str, Any]) -> StrictFirestore:
    store = StrictFirestore({_CONV_PATH: dict(snapshot)})
    monkeypatch.setattr(conversations_db, 'db', store)

    def _passthrough_transactional(function: Any) -> Any:
        return function

    monkeypatch.setattr(conversations_db.firestore, 'transactional', _passthrough_transactional)
    return store


def _row(store: StrictFirestore) -> Dict[str, Any]:
    return store.rows[_CONV_PATH]


# ---------------------------------------------------------------------------
# The trap: permissive read of an undecryptable enhanced blob is []
# ---------------------------------------------------------------------------


def test_permissive_read_decoder_maps_undecryptable_enhanced_to_empty_strict_raises() -> None:
    """The read path still degrades this blob to ``[]`` — that is the trap.

    red-proof: decode binding through ``_prepare_conversation_for_read``.
    """
    snapshot = _undecryptable_enhanced_snapshot()
    prepared = conversations_db._prepare_conversation_for_read(snapshot, _UID)  # pyright: ignore[reportPrivateUsage]
    assert prepared is not None
    assert prepared['transcript_segments'] == []
    assert transcript_sha256_for_binding([]) == EMPTY_DIGEST
    assert transcript_sha256([]) == EMPTY_DIGEST

    with pytest.raises((json.JSONDecodeError, TypeError, ValueError, zlib.error)):
        conversations_db._decode_transcript_segments_strict(  # pyright: ignore[reportPrivateUsage]
            _UID, snapshot['transcript_segments'], bool(snapshot.get('transcript_segments_compressed'))
        )


# ---------------------------------------------------------------------------
# Undecodable + empty-transcript digest: projection dropped, not stored
# ---------------------------------------------------------------------------


# red-proof: decode the transactional snapshot through _prepare_conversation_for_read
def test_undecryptable_enhanced_transcript_does_not_bind_empty_digest(caplog: pytest.LogCaptureFixture) -> None:
    snapshot = _undecryptable_enhanced_snapshot()
    mutation = _mutation(EMPTY_DIGEST, processing_admitted_at=_NOW)

    with caplog.at_level(logging.WARNING, logger=conversations_db.__name__):
        bound = conversations_db.extra_updates_with_bound_client_processing(_UID, snapshot, mutation)

    assert 'client_processing' not in bound
    assert bound['processing_admitted_at'] == _NOW
    warnings = [r for r in caplog.records if 'transcript_undecodable' in r.getMessage()]
    assert len(warnings) == 1
    assert CANARY not in warnings[0].getMessage()
    assert _SEGMENT_TEXT not in warnings[0].getMessage()


# red-proof: decode the transactional snapshot through _prepare_conversation_for_read
def test_undecryptable_enhanced_projection_is_not_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _install_strict_conversation_db(monkeypatch, _undecryptable_enhanced_snapshot())

    stored = conversations_db.bind_client_processing(_UID, _CONV_ID, _mutation(EMPTY_DIGEST))

    assert stored is False
    assert _row(store).get('client_processing') is None


# red-proof: let a decode exception propagate out of claim_conversation_status
def test_undecryptable_transcript_does_not_lose_the_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _install_strict_conversation_db(monkeypatch, _undecryptable_enhanced_snapshot())
    extra = _mutation(EMPTY_DIGEST, processing_admitted_at=_NOW)

    claimed = conversations_db.claim_conversation_status(
        _UID,
        _CONV_ID,
        ConversationStatus.in_progress,
        ConversationStatus.processing,
        extra_updates=extra,
    )

    assert claimed is True
    row = _row(store)
    assert row['status'] == ConversationStatus.processing.value
    assert row['processing_admitted_at'] == _NOW
    assert row.get('client_processing') is None
    assert row['structured']['title'] == _SEGMENT_TEXT


# red-proof: catch decode failure and still hash []
def test_corrupted_standard_compressed_bytes_do_not_bind_empty_digest() -> None:
    snapshot = _snapshot(
        {
            'transcript_segments': b'not-valid-zlib',
            'transcript_segments_compressed': True,
        },
        level='standard',
    )
    bound = conversations_db.extra_updates_with_bound_client_processing(_UID, snapshot, _mutation(EMPTY_DIGEST))
    assert 'client_processing' not in bound


# ---------------------------------------------------------------------------
# Genuinely empty transcript: we observed [], so the empty digest still binds
# ---------------------------------------------------------------------------


def test_genuinely_empty_encoded_transcript_binds_empty_digest() -> None:
    """Empty is a real transcript we can read, not a decrypt failure.

    Chosen behaviour: a write-path blob of ``[]`` (enhanced or standard)
    still stores a projection whose digest is the empty-transcript constant.
    We decoded the snapshot and it was empty; inventing a drop would punish a
    silent recording, which section 1.7 still finalizes. An *unreadable* blob
    is the opposite case and is dropped above.
    """
    for level in ('enhanced', 'standard'):
        encoded = _encode([], level=level)
        decoded = conversations_db._decode_transcript_segments_strict(  # pyright: ignore[reportPrivateUsage]
            _UID, encoded['transcript_segments'], bool(encoded.get('transcript_segments_compressed'))
        )
        assert decoded == []
        snapshot = _snapshot(encoded, level=level)
        bound = conversations_db.extra_updates_with_bound_client_processing(_UID, snapshot, _mutation(EMPTY_DIGEST))
        assert bound['client_processing']['transcript_sha256'] == EMPTY_DIGEST
        assert bound['client_processing']['structure']['title'] == CANARY


def test_genuinely_empty_plain_list_still_binds_empty_digest() -> None:
    """Legacy / test snapshots that hold a decoded ``[]`` list also bind."""
    snapshot = _snapshot({'transcript_segments': []}, level='standard')
    bound = conversations_db.extra_updates_with_bound_client_processing(_UID, snapshot, _mutation(EMPTY_DIGEST))
    assert bound['client_processing']['transcript_sha256'] == EMPTY_DIGEST


# ---------------------------------------------------------------------------
# Decodable transcript still binds normally
# ---------------------------------------------------------------------------


# red-proof: skip the transactional digest so a matching projection is dropped
def test_decodable_enhanced_transcript_binds_matching_digest() -> None:
    segments = _spoken_segments()
    expected = transcript_sha256_for_binding(segments)
    assert expected is not None
    encoded = _encode(segments, level='enhanced')
    snapshot = _snapshot(encoded, level='enhanced')

    bound = conversations_db.extra_updates_with_bound_client_processing(_UID, snapshot, _mutation(expected))
    assert bound['client_processing']['transcript_sha256'] == expected
    assert bound['client_processing']['structure']['title'] == CANARY


def test_decodable_transcript_rejects_empty_digest() -> None:
    """The empty digest is not a skeleton key for a readable non-empty row."""
    encoded = _encode(_spoken_segments(), level='enhanced')
    snapshot = _snapshot(encoded, level='enhanced')
    bound = conversations_db.extra_updates_with_bound_client_processing(_UID, snapshot, _mutation(EMPTY_DIGEST))
    assert 'client_processing' not in bound


def test_decodable_bind_stores_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    segments = _spoken_segments()
    expected = transcript_sha256_for_binding(segments)
    assert expected is not None
    encoded = _encode(segments, level='enhanced')
    store = _install_strict_conversation_db(
        monkeypatch, _snapshot(encoded, level='enhanced', status=ConversationStatus.completed.value)
    )

    stored = conversations_db.bind_client_processing(_UID, _CONV_ID, _mutation(expected))

    assert stored is True
    assert _row(store)['client_processing']['structure']['title'] == CANARY
    assert _row(store)['client_processing']['transcript_sha256'] == expected


# ---------------------------------------------------------------------------
# Round-7: non-canonical stored identity still fails closed after strict decode
# ---------------------------------------------------------------------------


# red-proof: bind through transcript_sha256 instead of transcript_sha256_for_binding
def test_legacy_padded_identity_still_fails_closed_after_strict_decode(caplog: pytest.LogCaptureFixture) -> None:
    legacy = {
        'id': 's1',
        'text': _SEGMENT_TEXT,
        'speaker': 'SPEAKER_00',
        'is_user': False,
        'person_id': ' alice ',
        'start': 0.0,
        'end': 1.0,
    }
    canonical = dict(legacy, person_id='alice')
    matching = transcript_sha256([canonical])
    assert matching == transcript_sha256([legacy])
    assert transcript_sha256_for_binding([legacy]) is None
    snapshot = _snapshot({'transcript_segments': [legacy]}, level='standard')

    with caplog.at_level(logging.WARNING, logger=conversations_db.__name__):
        bound = conversations_db.extra_updates_with_bound_client_processing(_UID, snapshot, _mutation(matching))

    assert 'client_processing' not in bound
    warnings = [r for r in caplog.records if 'stored_transcript_not_canonical' in r.getMessage()]
    assert len(warnings) == 1
    assert CANARY not in warnings[0].getMessage()
