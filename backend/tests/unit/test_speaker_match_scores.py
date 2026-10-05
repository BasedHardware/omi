"""Hermetic evidence snapshots: decisions, transport, codecs and bounded writes."""

import dataclasses
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

import utils.stt.speaker_match as policy
import config.speaker_match_scores as scores


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv('SPEAKER_MATCH_SCORES_ENABLED', 'true')
    # Import IO-ful dependencies in fixture setup, outside the per-test CPU budget.
    import database.conversations
    import routers.listen.speakers
    import utils.sync.speaker_identity
    import tests.unit.test_conversation_speaker_resolution_stage


def row(speaker=1, stage='capture', scope=''):
    distances = {'user': 0.412345, 'p': 0.723456}
    return scores.summarize(
        speaker, distances, policy.select_speaker_match(distances), 5.678912, stage, threshold=0.65, scope=scope
    )


def conversation(segments=None, **kwargs):
    import models.conversation as models

    defaults = {'started_at': None, 'finished_at': None, 'structured': {}}
    defaults.update(kwargs)
    return models.Conversation(
        id='c', created_at=datetime(2026, 10, 5, tzinfo=timezone.utc), transcript_segments=segments or [], **defaults
    )


def test_shape_rounding_nonfinite_and_margin():
    value = row()
    assert value == dict(
        speaker_id=1,
        speaker_id_scope='',
        owner_distance=0.412,
        person_distance=0.723,
        person_id='p',
        margin=0.311,
        evidence_seconds=5.679,
        status='user',
        decision='accepted',
        accepted_person_id='user',
        stage='capture',
        version=1,
        threshold=0.65,
        margin_threshold=0.1,
    )
    decision = policy.select_speaker_match({'user': float('nan')})
    missing = scores.summarize(2, {}, decision, None, 'sync', threshold=0.65)
    assert all(
        missing[k] is None for k in ('owner_distance', 'person_distance', 'person_id', 'margin', 'evidence_seconds')
    )
    json.dumps(missing, allow_nan=False)


def test_cap_and_latest_snapshot_per_stage_scope():
    rows = scores.merge(None, [row(i, stage) for stage in scores.STAGES for i in range(30)])
    assert len(rows) == 48
    assert all(sum(r['stage'] == stage for r in rows) == 16 for stage in scores.STAGES)
    updated = dict(rows[0], owner_distance=0.123)
    assert scores.merge(rows, [updated])[0] == updated
    assert len(scores.merge(None, [row(scope='a'), row(scope='b')])) == 2
    assert len(json.dumps(rows).encode()) < 24000


@pytest.mark.parametrize('stage,expected', [('dev', True), ('local', True), ('offline', True), ('prod', False)])
def test_rollout_default_and_kill_switch(monkeypatch, stage, expected):
    monkeypatch.delenv('SPEAKER_MATCH_SCORES_ENABLED')
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    assert scores.enabled() is expected
    monkeypatch.setenv('SPEAKER_MATCH_SCORES_ENABLED', 'typo')
    assert not scores.enabled()


def test_rounding_does_not_change_threshold_or_owner_arbitration():
    distances = {1: {'user': 0.649999}, 2: {'user': 0.650001}}
    decisions = {key: policy.select_speaker_match(ds) for key, ds in distances.items()}
    before = policy.arbitrate_owner_matches(distances, decisions)
    for key, decision in before.items():
        value = scores.summarize(key, distances[key], decision, 5, 'capture', threshold=0.65)
        assert value['owner_distance'] == 0.65
        assert value['accepted_person_id'] == decision.person_id
    assert before == policy.arbitrate_owner_matches(distances, decisions)
    assert before[1].owner_contended and before[2].person_id is None


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_model_storage_roundtrip_and_client_exclusion(monkeypatch, level):
    import database.conversations as db
    import models.transcript_segment as segments

    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    segment = segments.TranscriptSegment(
        id='s', text='synthetic', is_user=False, start=0, end=6, speaker_id=1, speaker_match_scores=row()
    )
    conv = conversation([segment])
    assert conv.speaker_match_scores == [row()]
    assert scores.FIELD not in conv.model_dump(mode='json')
    assert scores.FIELD not in segment.model_dump(mode='json')
    assert scores.FIELD not in segments.transcript_segment_for_client(segment.model_dump())
    assert scores.FIELD not in conv.model_json_schema()['properties']
    assert scores.FIELD not in segments.TranscriptSegment.model_json_schema()['properties']
    encoded = db.encode_conversation_for_write('u', conv.model_dump(), level)
    assert isinstance(encoded[scores.FIELD], str if level == 'enhanced' else bytes)
    decoded = db.prepare_conversation_for_read(dict(encoded, data_protection_level=level), 'u')
    restored = conversation(
        **{k: v for k, v in decoded.items() if k not in ('id', 'created_at', 'transcript_segments')},
        segments=decoded['transcript_segments']
    )
    assert restored.speaker_match_scores == [row()]
    assert scores.FIELD not in decoded['transcript_segments'][0]
    assert conversation().speaker_match_scores is None
    assert scores.FIELD not in conversation().model_dump()
    # Protection migration re-encodes the same evidence using the target level.
    other = 'enhanced' if level == 'standard' else 'standard'
    migrated = db.encode_conversation_for_write('u', decoded, other)
    assert db.prepare_conversation_for_read(dict(migrated, data_protection_level=other), 'u')[scores.FIELD] == [row()]


def test_capture_summary_piggybacks_identity_only_transaction(monkeypatch):
    import database.conversations as db
    import tests.unit.fixtures.strict_firestore_transaction as fixture

    store = fixture.StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s', text='synthetic', speaker_id=1, is_user=False, start=0, end=6)
    store.rows[path] = dict(id='c', transcript_segments=[segment], data_protection_level='standard')
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    db.update_conversation_segments(
        'u', 'c', [dict(segment, speaker_match_scores=row(), is_user=True)], segment_update_fields=('is_user',)
    )
    stored = db.prepare_conversation_for_read(store.rows[path], 'u')
    assert stored[scores.FIELD] == [row()]
    assert stored['transcript_segments'][0]['is_user'] is True
    assert scores.FIELD not in stored['transcript_segments'][0]
    db.update_conversation_segments('u', 'c', [dict(segment, speaker_match_scores=row(2, 'sync'))])
    assert len(db.prepare_conversation_for_read(store.rows[path], 'u')[scores.FIELD]) == 2


def test_sync_records_actual_evidence_without_extra_work(monkeypatch):
    import models.transcript_segment as models
    import utils.sync.speaker_identity as sync

    monkeypatch.setattr(sync, 'named_speaker_prompts_allowed', lambda uid: False)
    calls = []
    dependencies = dataclasses.replace(
        sync._DEFAULT_DEPS,
        speaker_embedding_configured=lambda: True,
        collect_speaker_audio=lambda *args: SimpleNamespace(clips=[(b'clip', 7.12345)], available_seconds=7.12345),
        extract_embedding_from_bytes=lambda *args: calls.append(args) or np.array([[1.0, 0.0]]),
        compare_embeddings=lambda *args: 0.412345,
    )
    segment = models.TranscriptSegment(id='s', speaker_id=1, text='synthetic', is_user=False, start=0, end=8)
    sync.identify_speakers_for_segments(
        [segment], b'fake', {'user': {'embedding': np.ones((1, 2)), 'name': 'Owner'}}, 'u', dependencies=dependencies
    )
    assert len(calls) == 1
    assert segment.is_user and segment.speaker_identity_status == 'user'
    assert segment.speaker_match_scores['stage'] == 'sync'
    assert segment.speaker_match_scores['evidence_seconds'] == 7.123
    assert conversation([segment]).speaker_match_scores == [segment.speaker_match_scores]


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_capture_computation_and_clear(monkeypatch, caplog):
    import routers.listen.speakers as live
    import utils.audio as audio

    ring = audio.AudioRingBuffer(60, 16000)
    ring.write_positioned(b'\x01\x00' * (10 * 16000), 100)
    host = SimpleNamespace(
        request=SimpleNamespace(uid='u', sample_rate=16000),
        state=SimpleNamespace(audio_ring_buffer=ring, speaker_id_enabled=True, current_conversation_id='c'),
        limits=SimpleNamespace(speaker_id_min_audio=2),
        emit_speaker_suggestion=lambda *a, **k: None,
    )
    matcher = live.SpeakerMatcher(host)
    matcher._profile_conversation_id = 'c'
    matcher.person_embeddings['user'] = {'name': 'Owner', 'embedding': np.ones((1, 2))}

    async def blocking(pool, fn, *args):
        return np.ones((1, 2))

    async def receipt(*args):
        return {}

    host.persistence = SimpleNamespace(call=receipt)
    monkeypatch.setattr(live, 'run_blocking', blocking)
    monkeypatch.setattr(live, 'compare_embeddings', lambda *args: 0.412345)
    await matcher.match(
        1, dict(id='s', conversation_id='c', abs_start=100.0, abs_end=110.0, duration=10.0, speaker_id_scope='live:c')
    )
    assert matcher.speaker_to_person.get(1, (None,))[0] == 'user', caplog.text
    assert matcher.match_scores[0]['owner_distance'] == 0.412
    assert matcher.match_scores[0]['evidence_seconds'] == 10
    matcher.clear()
    assert matcher.match_scores == []


def test_resolution_stage_and_cache_duration_no_replay(monkeypatch):
    import tests.unit.test_conversation_speaker_resolution_stage as fixtures
    import utils.conversations.speaker_resolution as stage

    store, diarizer = fixtures.env.__wrapped__(monkeypatch)
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda *a: {})
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda *a: fixtures.VOICES[0].tolist())
    plan = [0, 1] * 4
    fixtures._install_audio(monkeypatch, plan)
    conv = fixtures._conversation(plan)
    stage.resolve_speakers_for_processing('u', conv)
    assert conv.speaker_match_scores
    assert {r['stage'] for r in conv.speaker_match_scores} == {'resolution'}
    assert {r['threshold'] for r in conv.speaker_match_scores} == {0.5}
    assert all(r['evidence_seconds'] > 0 for r in conv.speaker_match_scores)
    calls = diarizer.calls
    replay = fixtures._conversation(plan)
    stage.resolve_speakers_for_processing('u', replay)
    assert diarizer.calls == calls
    assert replay.speaker_match_scores == conv.speaker_match_scores


def test_duplicate_person_summary_reports_the_final_sync_abstention():
    distances = {'p': 0.3, 'user': 0.9}
    decision = policy.select_speaker_match(distances)
    value = scores.summarize(
        2, distances, decision, 6, 'sync', threshold=0.65, accepted=False, outcome='duplicate_person'
    )
    assert decision.person_id == 'p'
    assert value['status'] == 'no_match'
    assert value['accepted_person_id'] is None
    assert value['decision'] == 'duplicate_person'


def test_flag_off_drops_new_evidence_and_preserves_old_scores(monkeypatch):
    import database.conversations as db

    monkeypatch.setenv('SPEAKER_MATCH_SCORES_ENABLED', 'false')
    data = {'transcript_segments': [{'speaker_match_scores': row()}]}
    assert scores.FIELD not in db.encode_conversation_for_write('u', data)
    existing = {'speaker_match_scores': [row()]}
    assert db.prepare_conversation_for_read(db.encode_conversation_for_write('u', existing), 'u')[scores.FIELD] == [
        row()
    ]


def test_cached_legacy_seconds_are_unknown_without_audio_replay():
    import utils.conversations.speaker_resolution as stage

    recovered = {}
    old = stage.encode_cache({'s': (60.0, np.array([1.0, 0.0]))})
    assert stage.decode_cache(old, recovered)
    assert recovered == {}
    saved = stage.encode_cache({'s': (60.0, np.array([1.0, 0.0]))}, {'s': 14.87654})
    assert stage.decode_cache(saved, recovered)['s'][0] == 60
    assert recovered == {'s': 14.877}


def test_live_score_only_update_does_not_advance_content_revision(monkeypatch):
    import database.conversations as db
    import tests.unit.fixtures.strict_firestore_transaction as fixture

    store = fixture.StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s', text='synthetic', speaker_id=1, is_user=False, start=0, end=6)
    store.rows[path] = dict(
        id='c',
        transcript_segments=[segment],
        data_protection_level='standard',
        sync_live_target=True,
        sync_content_revision=7,
    )
    scored = dict(segment, speaker_match_scores=row())
    planned = SimpleNamespace(segments=[scored], absorbed_into={}, with_segments=lambda accepted: accepted)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(db, 'merge_live_segments', lambda *args, **kwargs: planned)
    monkeypatch.setattr(db, 'sync_lineage_resolve_active_for', lambda uid: True)
    result = db.update_conversation_segments('u', 'c', [scored], live_segments=[scored])
    assert store.rows[path]['sync_content_revision'] == 7
    assert scores.FIELD not in result[0]
    assert db.prepare_conversation_for_read(store.rows[path], 'u')[scores.FIELD] == [row()]
