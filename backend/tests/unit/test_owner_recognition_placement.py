"""Finalized transcript identity survives a missing source-frame receipt."""

import numpy as np
from datetime import datetime, timezone, timedelta
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot

from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    empty_manual_receipt,
    _span_flags,
    _install_audio,
    _capture_shifted_conversation,
    VOICES,
)
from utils.conversations import speaker_resolution as stage
from utils.stt.conversation_speakers import resolve_conversation_speakers


def test_partial_live_owner_with_unknown_client_source_receipt(env, monkeypatch):
    _span_flags(monkeypatch)
    _, diarizer = env
    plan = [0] * 4
    _install_audio(monkeypatch, plan, offset=180.0)
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: VOICES[0].tolist())
    conversation = _capture_shifted_conversation(plan)
    conversation.capture_evidence = {
        'version': 1,
        'origin': 'live',
        'reason': 'missing_source_position',
        'coverage': 'unknown',
        'capability': 'unknown',
    }
    missing = conversation.transcript_segments[-1]
    missing.audio_capture_start = missing.audio_capture_end = None
    stage.resolve_speakers_for_processing('u1', conversation)
    payload = conversation.model_dump()
    assert [s['is_user'] for s in payload['transcript_segments']] == [True, True, True, False]
    assert payload['speaker_resolution']['status'] == 'unavailable'
    assert diarizer.calls == 3


def test_clipped_embedding_duration_is_the_owner_evidence_floor():
    segments = [{'id': 'long', 'speaker_id': 0, 'start': 0.0, 'end': 30.0, 'is_user': False}]
    resolution = resolve_conversation_speakers(
        segments, {'long': np.array([1.0, 0.0])}, voiceprints={'user': [1.0, 0.0]}, embedding_seconds={'long': 1.0}
    )
    assert not resolution.voice_identities


def test_late_audio_retry_persists_identity_without_processing(env, monkeypatch):
    conversation = _capture_shifted_conversation([0, 0])
    conversation.status = 'completed'
    raw = conversation.model_dump()
    raw['updated_at'] = conversation.created_at
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', lambda *a: raw)
    writes = []

    def resolve(uid, conv, **kwargs):
        conv.transcript_segments[0].is_user = True
        return True

    monkeypatch.setattr(stage, 'resolve_speakers_for_processing', resolve)
    monkeypatch.setattr(
        stage.conversations_db,
        'persist_speaker_resolution_if_current',
        lambda uid, payload, **kw: writes.append((payload, kw)) or True,
    )
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    assert writes[0][0]['transcript_segments'][0]['is_user'] is True
    assert writes[0][1]['expected_updated_at'] == raw['updated_at']


def test_late_audio_identity_commit_refuses_intervening_manual_write(monkeypatch):
    store = StrictFirestore()
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        StrictFirestoreSnapshot,
        'update_time',
        property(lambda snap: (snap.to_dict() or {}).get('test_revision')),
        raising=False,
    )
    monkeypatch.setattr(stage.conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(stage.conversations_db, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(stage.conversations_db, '_sync_conversation_search_index', lambda *a: None)
    payload = {
        'id': 'c1',
        'transcript_segments': [
            {
                'id': 's',
                'speaker_id': 0,
                'speaker': 'SPEAKER_0',
                'start': 0.0,
                'end': 6.0,
                'text': 'hi',
                'is_user': True,
            }
        ],
        'data_protection_level': 'standard',
    }
    path = ('users', 'u1', 'conversations', 'c1')
    store.rows[path] = {
        'status': 'completed',
        'test_revision': at + timedelta(seconds=1),
        'data_protection_level': 'standard',
    }
    assert not stage.conversations_db.persist_speaker_resolution_if_current('u1', payload, expected_updated_at=at)
    assert 'transcript_segments' not in store.rows[path]
    store.rows[path]['test_revision'] = at
    assert stage.conversations_db.persist_speaker_resolution_if_current('u1', payload, expected_updated_at=at)
    decoded = stage.conversations_db._decode_transcript_segments_strict(
        'u1', store.rows[path]['transcript_segments'], bool(store.rows[path].get('transcript_segments_compressed'))
    )
    assert decoded[0]['is_user'] is True
    store.rows[('account_deletions', 'u1')] = {'wipe_status': 'pending'}
    assert not stage.conversations_db.persist_speaker_resolution_if_current('u1', payload, expected_updated_at=at)
