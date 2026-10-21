"""Physical audio cleanup when a listen generation is deleted as empty (#11742).

The emptiness guard that authorizes the delete consults transcript segments,
photos and ``has_content`` — never ``audio_files``. A generation whose STT
produced nothing while the provider was failing therefore reaches the delete
with real, registered audio on it, so cleanup here cannot be unconditional.
"""

from __future__ import annotations

from typing import Any

import pytest

from utils.conversations import lifecycle as lifecycle_mod


def _tombstone_returning(deleted: bool, conversation: dict[str, Any] | None = None):
    """Stand in for the transaction, honouring its published-snapshot contract."""

    def _tombstone(
        uid: str,
        conversation_id: str,
        recording_session_id: str | None,
        *,
        firestore_client: Any = None,
        deleted_conversation: dict[str, Any] | None = None,
    ) -> bool:
        if deleted and deleted_conversation is not None:
            deleted_conversation.clear()
            deleted_conversation.update(conversation or {})
        return deleted

    return _tombstone


@pytest.fixture
def cleanup_seam(monkeypatch):
    """Hold the two physical-cleanup boundaries and the fallback emitter."""
    calls: dict[str, list[Any]] = {'audio': [], 'photos': [], 'fallback': []}

    # raising=False so this file fails on the missing *behaviour* rather than on
    # a missing attribute when run against a tree without the cleanup call.
    monkeypatch.setattr(
        lifecycle_mod,
        'delete_conversation_audio_files',
        lambda uid, conversation_id: calls['audio'].append((uid, conversation_id)),
        raising=False,
    )
    monkeypatch.setattr(
        lifecycle_mod.conversations_db,
        'delete_conversation_photos',
        lambda uid, conversation_id: calls['photos'].append((uid, conversation_id)),
    )
    monkeypatch.setattr(
        lifecycle_mod,
        'record_fallback',
        lambda **kwargs: calls['fallback'].append(kwargs),
    )
    return calls


def test_empty_generation_without_registered_audio_reclaims_its_chunks(monkeypatch, cleanup_seam):
    """Nothing ever referenced these bytes, and the row that could have is gone."""
    monkeypatch.setattr(
        lifecycle_mod.recording_sessions_db,
        'tombstone_and_delete_empty_conversation',
        _tombstone_returning(True, {'id': 'conversation', 'status': 'in_progress'}),
    )

    deleted = lifecycle_mod.delete_empty_recording_conversation('uid', 'conversation', 'recording')

    assert deleted is True
    assert cleanup_seam['audio'] == [('uid', 'conversation')]
    assert cleanup_seam['photos'] == [('uid', 'conversation')]


def test_empty_generation_with_registered_audio_keeps_its_recording(monkeypatch, cleanup_seam):
    """The STT-failure case: the only surviving copy of a real recording stays."""
    monkeypatch.setattr(
        lifecycle_mod.recording_sessions_db,
        'tombstone_and_delete_empty_conversation',
        _tombstone_returning(
            True,
            {
                'id': 'conversation',
                'status': 'in_progress',
                'audio_files': [{'path': 'chunks/uid/conversation/0.wav'}],
            },
        ),
    )

    deleted = lifecycle_mod.delete_empty_recording_conversation('uid', 'conversation', 'recording')

    assert deleted is True
    assert cleanup_seam['audio'] == []
    # The row still goes away; only the bytes are spared.
    assert cleanup_seam['photos'] == [('uid', 'conversation')]


def test_a_refused_delete_never_touches_audio(monkeypatch, cleanup_seam):
    """Late content won the transaction, so the conversation still owns its audio."""
    monkeypatch.setattr(
        lifecycle_mod.recording_sessions_db,
        'tombstone_and_delete_empty_conversation',
        _tombstone_returning(False),
    )

    deleted = lifecycle_mod.delete_empty_recording_conversation('uid', 'conversation', 'recording')

    assert deleted is False
    assert cleanup_seam['audio'] == []
    assert cleanup_seam['photos'] == []


def test_a_failed_sweep_is_reported_without_breaking_the_delete(monkeypatch, cleanup_seam):
    """A GCS failure leaves the orphan behind; it must not resurrect the row."""

    def _boom(uid: str, conversation_id: str) -> None:
        raise RuntimeError('gcs unavailable')

    monkeypatch.setattr(lifecycle_mod, 'delete_conversation_audio_files', _boom, raising=False)
    monkeypatch.setattr(
        lifecycle_mod.recording_sessions_db,
        'tombstone_and_delete_empty_conversation',
        _tombstone_returning(True, {'id': 'conversation', 'status': 'in_progress'}),
    )

    deleted = lifecycle_mod.delete_empty_recording_conversation('uid', 'conversation', 'recording')

    assert deleted is True
    assert len(cleanup_seam['fallback']) == 1
    assert cleanup_seam['fallback'][0]['outcome'] == 'exhausted'
