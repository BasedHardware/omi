"""Late recognition observes the readable identities actually committed by CAS."""

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot
from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    empty_manual_receipt,
    _capture_shifted_conversation,
    _install_audio,
    _span_flags,
    VOICES,
)
from utils.conversations import speaker_resolution as stage
from utils.observability import owner_recognition as metrics


def _counter(outcome):
    return metrics.OWNER_IDENTITY_REPAIR.labels(outcome=outcome)._value.get()


def _commit_store(monkeypatch, conversation, level, *, receipt=None, omit_ids=False, omit_identity_fields=()):
    store = StrictFirestore()
    at = conversation.created_at
    monkeypatch.setattr(StrictFirestoreSnapshot, 'update_time', property(lambda s: at), raising=False)
    monkeypatch.setattr(stage.identity_updates_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(stage.conversations_db, 'invalidate_people_stats_cache', lambda *a: None)
    raw = conversation.model_dump()
    raw.update(status='completed', data_protection_level=level)
    if omit_ids:
        for segment in raw['transcript_segments']:
            segment.pop('id', None)
    for segment in raw['transcript_segments']:
        for field in omit_identity_fields:
            segment.pop(field, None)
    if receipt:
        raw['manual_speaker_assignments'] = receipt
    path = ('users', 'u1', 'conversations', 'c1')
    store.rows[path] = stage.conversations_db.encode_conversation_for_write('u1', raw, level)

    def read(*args):
        result = stage.conversations_db.prepare_conversation_for_read(store.rows[path], 'u1')
        result['updated_at'] = at
        return result

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    return store, path, read


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_late_legacy_cache_acquires_real_evidence_and_persists_owner(env, monkeypatch, level):
    cache, diarizer = env
    _span_flags(monkeypatch)
    _install_audio(monkeypatch, [0, 0], offset=180.0)
    conversation = _capture_shifted_conversation([0, 0])
    for segment in conversation.transcript_segments:
        segment.speaker_id_scope = 'conversation:c1'
    cache['c1'] = stage.encode_cache({s.id: (s.end - s.start, VOICES[0]) for s in conversation.transcript_segments})
    legacy_bytes = cache['c1']
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: VOICES[0].tolist())
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda uid: False)
    monkeypatch.setattr(stage.users_db, 'get_people', lambda uid: pytest.fail('free owner repair reads paid people'))
    store, path, read = _commit_store(monkeypatch, conversation, level)
    before = _counter('owner_added')
    assert not any(s['is_user'] for s in read()['transcript_segments'])
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    # Real compressed/encrypted write -> canonical read -> client transcript.
    assert all(s['is_user'] for s in read()['transcript_segments'])
    assert diarizer.calls == 2
    assert _counter('owner_added') == before + 1
    durations = {}
    stage.decode_cache(cache['c1'], durations)
    assert sum(durations.values()) >= 5
    assert cache['c1'] != legacy_bytes
    assert not stage.refresh_completed_speaker_identity('u1', 'c1')
    assert diarizer.calls == 2 and _counter('owner_added') == before + 1


@pytest.mark.parametrize('measured', [0.0, -1.0, float('nan'), float('inf'), 3.8])
def test_placeable_cache_refreshes_only_unknown_or_invalid_evidence(env, monkeypatch, measured):
    cache, diarizer = env
    _span_flags(monkeypatch)
    _install_audio(monkeypatch, [0, 0], offset=180.0)
    conversation = _capture_shifted_conversation([0, 0])
    for segment in conversation.transcript_segments:
        segment.speaker_id_scope = 'conversation:c1'
    cache['c1'] = stage.encode_cache(
        {s.id: (s.end - s.start, VOICES[0]) for s in conversation.transcript_segments},
        {s.id: measured for s in conversation.transcript_segments},
    )
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: VOICES[0].tolist())
    stage.resolve_speakers_for_processing('u1', conversation)
    assert all(s.is_user for s in conversation.transcript_segments)
    assert diarizer.calls == (0 if measured == 3.8 else 2)


def test_legacy_evidence_refresh_failure_preserves_grouping_without_claiming_owner(env, monkeypatch):
    cache, diarizer = env
    _span_flags(monkeypatch)
    _install_audio(monkeypatch, [0, 0], offset=180.0)
    conversation = _capture_shifted_conversation([0, 0])
    for segment in conversation.transcript_segments:
        segment.speaker_id_scope = 'conversation:c1'
    cache['c1'] = stage.encode_cache({s.id: (s.end - s.start, VOICES[0]) for s in conversation.transcript_segments})
    original = cache['c1']
    diarizer.fail = True
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: VOICES[0].tolist())
    stage.resolve_speakers_for_processing('u1', conversation, max_embedding_attempts=1)
    assert diarizer.calls == 1
    assert cache['c1'] == original
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 1
    assert not any(s.is_user for s in conversation.transcript_segments)
