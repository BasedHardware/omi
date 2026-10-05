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
    import routers.listen.transcripts
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
        segments=decoded['transcript_segments'],
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


@pytest.mark.parametrize('score_fails', [False, True])
def test_sync_records_actual_evidence_without_extra_work(monkeypatch, score_fails):
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
    if score_fails:
        monkeypatch.setattr(scores, 'summarize', lambda *a, **k: (_ for _ in ()).throw(ValueError('score fault')))
    sync.identify_speakers_for_segments(
        [segment], b'fake', {'user': {'embedding': np.ones((1, 2)), 'name': 'Owner'}}, 'u', dependencies=dependencies
    )
    assert len(calls) == 1
    assert segment.is_user and segment.speaker_identity_status == 'user'
    if score_fails:
        assert segment.speaker_match_scores is None
        return
    assert segment.speaker_match_scores['stage'] == 'sync'
    assert segment.speaker_match_scores['evidence_seconds'] == 7.123
    assert conversation([segment]).speaker_match_scores == [segment.speaker_match_scores]


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
@pytest.mark.parametrize(
    'case',
    [
        'automatic',
        'score_fault',
        'manual',
        'manual_other',
        'manual_score_fault',
        'manual_rejected',
        'manual_rejected_fault',
    ],
)
async def test_capture_computation_and_clear(monkeypatch, caplog, case):
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
        return (
            {
                'speakers': {
                    '1': {
                        'is_user': case != 'manual_other',
                        'person_id': 'p' if case == 'manual_other' else None,
                        'source': 'manual',
                        'rejection': case.startswith('manual_rejected'),
                    }
                }
            }
            if case.startswith('manual')
            else {}
        )

    host.persistence = SimpleNamespace(call=receipt)
    monkeypatch.setattr(live, 'run_blocking', blocking)
    monkeypatch.setattr(live, 'compare_embeddings', lambda *args: 0.412345)
    if 'fault' in case:
        monkeypatch.setattr(scores, 'summarize', lambda *a, **k: (_ for _ in ()).throw(ValueError('score fault')))
    await matcher.match(
        1, dict(id='s', conversation_id='c', abs_start=100.0, abs_end=110.0, duration=10.0, speaker_id_scope='live:c')
    )
    if case.startswith('manual_rejected'):
        assert 1 not in matcher.speaker_to_person
        assert matcher.voice_identity_status[1] == 'no_match'
        assert host.state.speaker_map_dirty
        if 'fault' in case:
            assert matcher.match_scores == []
        else:
            assert matcher.match_scores[0]['decision'] == 'manual_rejected'
            assert matcher.match_scores[0]['accepted_person_id'] is None
            assert matcher.match_scores[0]['owner_distance'] == 0.412
        return
    assert matcher.speaker_to_person.get(1, (None,))[0] == ('p' if case == 'manual_other' else 'user'), caplog.text
    assert matcher.voice_identity_status[1] == ('not_user' if case == 'manual_other' else 'user')
    assert host.state.speaker_map_dirty
    if 'fault' in case:
        assert matcher.match_scores == []
    else:
        assert matcher.match_scores[0]['owner_distance'] == 0.412
        assert matcher.match_scores[0]['evidence_seconds'] == 10
        assert matcher.match_scores[0]['accepted_person_id'] == ('p' if case == 'manual_other' else 'user')
        assert matcher.match_scores[0]['decision'] == ('manual_decision' if case.startswith('manual') else 'accepted')
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


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_worst_case_encoded_growth_is_capped(monkeypatch, level):
    import random
    import database.conversations as db
    import utils.firestore_document_size as size

    rng = random.Random(7)
    rows = []
    for stage in scores.STAGES:
        for speaker in range(16):
            value = row(speaker, stage, ''.join(chr(rng.randrange(0x1000, 0x9000)) for _ in range(128)))
            value.update(person_id=''.join(chr(rng.randrange(0x1000, 0x9000)) for _ in range(128)))
            rows.append(value)
    # Low-compressibility Unicode exercises JSON escaping and encryption's
    # hex/base64 expansion, rather than measuring just repeated fixture rows.
    data = {'id': 'c', 'speaker_match_scores': rows}
    encoded = db.encode_conversation_for_write('u', data, level)
    blob = encoded[scores.FIELD]
    bytes_used = len(blob.encode()) if isinstance(blob, str) else len(blob)
    assert bytes_used <= 8192
    decoded = db.prepare_conversation_for_read(dict(encoded, data_protection_level=level), 'u')
    assert 0 < len(decoded[scores.FIELD]) < 48
    baseline = {k: v for k, v in encoded.items() if k != scores.FIELD}
    delta = size.estimate_firestore_document_bytes(encoded, None) - size.estimate_firestore_document_bytes(
        baseline, None
    )
    assert delta <= 8214


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_score_encoding_failure_never_blocks_content_commit(monkeypatch, level):
    import utils.observability.fallback as fallback

    import database.conversations as db
    import tests.unit.fixtures.strict_firestore_transaction as fixture

    store = fixture.StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s', text='before', speaker_id=1, is_user=False, start=0, end=6)
    store.rows[path] = dict(id='c', transcript_segments=[segment], data_protection_level=level)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    original = db._protect_json_value
    events = []
    monkeypatch.setattr(fallback, 'record_fallback', lambda **kwargs: events.append(kwargs))

    def fail_scores(value, uid, protection):
        if isinstance(value, list) and value and 'stage' in value[0]:
            raise RuntimeError('synthetic score codec failure')
        return original(value, uid, protection)

    monkeypatch.setattr(db, '_protect_json_value', fail_scores)
    db.update_conversation_segments('u', 'c', [dict(segment, text='after', speaker_match_scores=row())])
    raw = store.rows[path]
    assert scores.FIELD not in raw
    assert isinstance(raw['transcript_segments'], str if level == 'enhanced' else bytes)
    assert db.prepare_conversation_for_read(raw, 'u')['transcript_segments'][0]['text'] == 'after'
    assert events[-1]['to_mode'] == 'scores_omitted'


def test_near_full_document_omits_scores_using_existing_snapshot(monkeypatch):
    import database.conversations as db
    import tests.unit.fixtures.strict_firestore_transaction as fixture

    store = fixture.StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s', text='before', speaker_id=1, is_user=False, start=0, end=6)
    store.rows[path] = dict(
        id='c', transcript_segments=[segment], data_protection_level='standard', other_metadata='x' * (900 * 1024)
    )
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    db.update_conversation_segments('u', 'c', [dict(segment, text='after', speaker_match_scores=row())])
    assert scores.FIELD not in store.rows[path]
    assert db.prepare_conversation_for_read(store.rows[path], 'u')['transcript_segments'][0]['text'] == 'after'


@pytest.mark.parametrize('bad', [[{'stage': 'capture'}], [{'stage': 'capture', 'speaker_id': [], 'margin': object()}]])
def test_malformed_optional_scores_never_block_content(bad):
    import database.conversations as db

    encoded = db.encode_conversation_for_write('u', dict(speaker_match_scores=bad, transcript_segments=[]))
    assert scores.FIELD not in encoded
    assert db.prepare_conversation_for_read(encoded, 'u')['transcript_segments'] == []


@pytest.mark.parametrize('source,target', [('standard', 'enhanced'), ('enhanced', 'standard')])
@pytest.mark.parametrize('codec_fails', [False, True])
def test_real_protection_migration_preserves_or_deletes_optional_scores(monkeypatch, source, target, codec_fails):
    import database.conversations as db
    import tests.unit.fixtures.strict_firestore_transaction as fixture

    store = fixture.StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    store.rows[path] = db.encode_conversation_for_write(
        'u', dict(id='c', transcript_segments=[], data_protection_level=source, speaker_match_scores=[row()]), source
    )

    def get_all(refs, field_paths):
        for ref in refs:
            snap = ref.get()
            snap.reference = ref
            snap.id = 'c'
            yield snap

    monkeypatch.setattr(store, 'get_all', get_all, raising=False)
    monkeypatch.setattr(store, 'batch', lambda: SimpleNamespace(), raising=False)
    monkeypatch.setattr(
        fixture.StrictFirestoreCollection,
        'select',
        lambda self, fields: SimpleNamespace(stream=lambda: []),
        raising=False,
    )
    monkeypatch.setattr(db, 'db', store)
    original = db._protect_json_value

    def protect(value, uid, level):
        if codec_fails and isinstance(value, list) and value and 'stage' in value[0]:
            raise RuntimeError('synthetic score migration failure')
        return original(value, uid, level)

    monkeypatch.setattr(db, '_protect_json_value', protect)
    db.migrate_conversations_level_batch('u', ['c'], target)
    raw = store.rows[path]
    assert raw['data_protection_level'] == target
    assert isinstance(raw['transcript_segments'], str if target == 'enhanced' else bytes)
    if codec_fails:
        # The strict fixture retains sentinels; this is Firestore's field delete.
        assert raw[scores.FIELD] is db.firestore.DELETE_FIELD
    else:
        assert isinstance(raw[scores.FIELD], str if target == 'enhanced' else bytes)
        assert db.prepare_conversation_for_read(raw, 'u')[scores.FIELD] == [row()]


@pytest.mark.parametrize('failure', ['decode', 'size_estimation'])
def test_optional_score_faults_leave_content_write_successful(monkeypatch, failure):
    import database.conversations as db
    import tests.unit.fixtures.strict_firestore_transaction as fixture

    store = fixture.StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s', text='before', speaker_id=1, is_user=False, start=0, end=6)
    store.rows[path] = db.encode_conversation_for_write(
        'u', dict(id='c', transcript_segments=[segment], data_protection_level='standard', speaker_match_scores=[row()])
    )
    original = db._reveal_json_value
    old_blob = store.rows[path][scores.FIELD]
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)

    def fail(*args, **kwargs):
        raise RuntimeError('synthetic optional score fault')

    if failure == 'decode':
        monkeypatch.setattr(
            db, '_reveal_json_value', lambda raw, *args: fail() if raw == old_blob else original(raw, *args)
        )
    else:
        monkeypatch.setattr(db.document_size, 'estimate_firestore_document_bytes', fail)
    db.update_conversation_segments('u', 'c', [dict(segment, text='after', speaker_match_scores=row())])
    assert (
        db._decode_transcript_segments_strict('u', store.rows[path]['transcript_segments'], True)[0]['text'] == 'after'
    )


@pytest.mark.parametrize('source,target', [('standard', 'enhanced'), ('enhanced', 'standard')])
@pytest.mark.parametrize('codec_fails', [False, True])
def test_processing_snapshot_scores_follow_current_transaction_protection(monkeypatch, source, target, codec_fails):
    import database.conversations as db

    write_data = db.encode_conversation_for_write(
        'u', dict(transcript_segments=[], data_protection_level=source, speaker_match_scores=[row()]), source
    )
    original = db._protect_json_value

    def protect(value, uid, level):
        if codec_fails and isinstance(value, list) and value and 'stage' in value[0]:
            raise RuntimeError('synthetic score re-encoding failure')
        return original(value, uid, level)

    monkeypatch.setattr(db, '_protect_json_value', protect)
    # This exact helper is called inside both processing-result transactions
    # after they read the current document, including concurrent migrations.
    db._reapply_current_manual_assignments('u', write_data, {'data_protection_level': target})
    assert write_data['data_protection_level'] == target
    assert isinstance(write_data['transcript_segments'], str if target == 'enhanced' else bytes)
    if codec_fails:
        assert scores.FIELD not in write_data
    else:
        assert isinstance(write_data[scores.FIELD], str if target == 'enhanced' else bytes)
        assert db.prepare_conversation_for_read(write_data, 'u')[scores.FIELD] == [row()]


@pytest.mark.parametrize('bad', [{'stage': 'capture'}, {'stage': 'capture', 'speaker_id': []}])
def test_malformed_segment_score_does_not_abort_conversation(bad):
    import models.transcript_segment as models

    segment = models.TranscriptSegment(
        id='s', text='kept', is_user=False, start=0, end=6, speaker_id=1, speaker_match_scores=bad
    )
    conv = conversation([segment], speaker_match_scores=[row()])
    assert conv.speaker_match_scores is None
    assert conv.transcript_segments[0].text == 'kept'
    assert scores.FIELD not in conv.model_dump()


def test_malformed_score_mutation_does_not_abort_model_serialization():
    conv = conversation()
    conv.speaker_match_scores = [{'stage': 'capture'}]
    assert scores.FIELD not in conv.model_dump()
    assert scores.FIELD not in conv.model_dump(mode='json')


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_processing_scores_keep_concurrent_rows_and_replace_resolution(level):
    import database.conversations as db

    latest = dict(row(1), owner_distance=0.2)
    current_rows = [latest, row(2, 'sync'), row(7, 'resolution')]
    snapshot_rows = [row(1), row(3, 'capture'), row(8, 'resolution')]
    existing = db.encode_conversation_for_write('u', dict(speaker_match_scores=current_rows), level)
    existing['data_protection_level'] = level
    update = db.encode_conversation_for_write(
        'u', dict(transcript_segments=[], speaker_match_scores=snapshot_rows), level
    )
    db._reapply_current_manual_assignments('u', update, existing)
    decoded = db.prepare_conversation_for_read(update, 'u')[scores.FIELD]
    assert latest in decoded
    assert row(2, 'sync') in decoded
    assert row(3, 'capture') in decoded
    assert row(8, 'resolution') in decoded
    assert row(7, 'resolution') not in decoded


def test_processing_score_cap_prioritizes_current_capture_rows():
    current = [row(i, 'capture') for i in range(16, 32)]
    snapshot = [row(i, 'capture') for i in range(16)]
    assert scores.merge_processing(current, snapshot) == current


@pytest.mark.parametrize('fault', ['current_decode', 'merge'])
def test_processing_optional_merge_failure_keeps_current_blob(monkeypatch, fault):
    import database.conversations as db

    existing = db.encode_conversation_for_write('u', dict(speaker_match_scores=[row(2, 'sync')]))
    before = dict(existing)
    update = db.encode_conversation_for_write('u', dict(transcript_segments=[], speaker_match_scores=[row()]))
    if fault == 'current_decode':
        existing[scores.FIELD] = b'corrupt'
        before = dict(existing)
    else:
        monkeypatch.setattr(scores, 'merge_processing', lambda *a: (_ for _ in ()).throw(ValueError('merge fault')))
    db._reapply_current_manual_assignments('u', update, existing)
    assert scores.FIELD not in update
    assert db.prepare_conversation_for_read(update, 'u')['transcript_segments'] == []
    assert existing == before


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_sync_bridge_aggregates_decoded_donor_scores(monkeypatch, level):
    import database.conversations as db
    import tests.unit.fixtures.strict_firestore_transaction as fixture
    import tests.unit.test_sync_cross_job_assignment as sync_fixtures

    store = fixture.StrictFirestore()
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(db, '_delete_conversation_search_index', lambda *a: None)
    for cid, start, stage in [('a', 1000, 'capture'), ('b', 1240, 'sync')]:
        data = sync_fixtures.chunk(cid, start)
        data.update(data_protection_level=level, speaker_match_scores=[row(1, stage, scope=cid)])
        db.assign_sync_conversation('u', data, firestore_client=store)
    incoming = sync_fixtures.chunk('bridge', 1120)
    incoming['data_protection_level'] = level
    result, _, _ = db.assign_sync_conversation('u', incoming, firestore_client=store)
    stored = db.prepare_conversation_for_read(store.rows[('users', 'u', 'conversations', result['id'])], 'u')
    assert {r['speaker_id_scope'] for r in stored[scores.FIELD]} == {'a', 'b'}
    assert len(stored['transcript_segments']) == 3
    assert isinstance(
        store.rows[('users', 'u', 'conversations', result['id'])][scores.FIELD], str if level == 'enhanced' else bytes
    )


@pytest.mark.parametrize('retains_rows', [True, False])
def test_trim_telemetry_distinguishes_partial_retention(monkeypatch, retains_rows):
    import utils.observability.fallback as fallback

    import database.conversations as db

    events = []
    monkeypatch.setattr(fallback, 'record_fallback', lambda **kw: events.append(kw))
    encoded = db._protect_json_value([row()], 'u', 'standard') if retains_rows else None
    monkeypatch.setattr(scores, 'encode_bounded', lambda *a: (encoded, True))
    result = db.encode_conversation_for_write('u', dict(transcript_segments=[], speaker_match_scores=[row()]))
    assert (scores.FIELD in result) == retains_rows
    assert events[-1]['to_mode'] == ('scores_trimmed' if retains_rows else 'scores_omitted')


@pytest.mark.parametrize('fault', ['summarize', 'publish'])
def test_optional_resolution_scores_never_block_voice_application(monkeypatch, fault):
    import tests.unit.test_conversation_speaker_resolution_stage as fixtures
    import utils.conversations.speaker_resolution as stage

    fixtures.env.__wrapped__(monkeypatch)
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda *a: {})
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda *a: fixtures.VOICES[0].tolist())
    plan = [0, 1] * 4
    fixtures._install_audio(monkeypatch, plan)
    conv = fixtures._conversation(plan)
    original = scores.merge
    if fault == 'summarize':
        monkeypatch.setattr(scores, 'summarize', lambda *a, **k: (_ for _ in ()).throw(ValueError('score fault')))
    else:

        def merge(existing, updates):
            if existing is not None:
                raise ValueError('score publication fault')
            return original(existing, updates)

        monkeypatch.setattr(scores, 'merge', merge)
    stage.resolve_speakers_for_processing('u', conv)
    assert conv.speaker_resolution.status == 'resolved'
    assert any(s.is_user for s in conv.transcript_segments)


def test_malformed_capture_score_does_not_abort_segment_identity_status():
    import routers.listen.transcripts as transcripts
    import models.transcript_segment as models

    speaker = SimpleNamespace(
        match_scores=[{'stage': 'capture'}],
        segment_assignments={'s': 'user'},
        speaker_to_person={},
        voice_identity_status={},
        segment_identity_status={},
    )
    processor = SimpleNamespace(host=SimpleNamespace(speakers=speaker))
    segment = models.TranscriptSegment(id='s', text='kept', is_user=True, start=0, end=6, speaker_id=1)
    transcripts.TranscriptProcessor._apply_speaker_identity_statuses(processor, [segment])
    assert segment.speaker_identity_status == 'user'
    assert segment.text == 'kept'


def test_malformed_cache_evidence_keeps_embeddings():
    import struct
    import utils.conversations.speaker_resolution as stage

    cache = {'s': (6.0, np.ones(3))}
    raw = stage.encode_cache(cache, {'s': object()})
    size = struct.unpack('>I', raw[:4])[0]
    header = json.loads(raw[4 : 4 + size])
    header['evidence_seconds'] = 42
    encoded = json.dumps(header).encode()
    raw = struct.pack('>I', len(encoded)) + encoded + raw[4 + size :]
    decoded = stage.decode_cache(raw, {})
    assert decoded['s'][0] == 6.0
    np.testing.assert_array_equal(decoded['s'][1], cache['s'][1])


def test_bad_embedding_seconds_does_not_change_resolved_voice():
    import tests.unit.test_conversation_speakers as fixture
    import utils.stt.conversation_speakers as resolver

    segments, embeddings, voices = fixture._fragmented([0] * 4)
    before = resolver.resolve_conversation_speakers(segments, embeddings, voiceprints={'user': voices[0]})
    after = resolver.resolve_conversation_speakers(
        segments, embeddings, voiceprints={'user': voices[0]}, embedding_seconds={s['id']: 'invalid' for s in segments}
    )
    assert after.speaker_ids == before.speaker_ids
    assert after.voice_identities == before.voice_identities


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('bad', [{}, [42], [row(), None], [{'stage': 'capture'}]])
def test_invalid_decoded_score_shape_cannot_break_conversation(level, bad):
    import database.conversations as db

    raw = db.encode_conversation_for_write('u', dict(transcript_segments=[], data_protection_level=level), level)
    raw[scores.FIELD] = db._protect_json_value(bad, 'u', level)
    decoded = db.prepare_conversation_for_read(raw, 'u')
    assert scores.FIELD not in decoded
    assert conversation(segments=decoded['transcript_segments']).speaker_match_scores is None


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('new_scores', [True, False])
def test_capacity_guard_deletes_existing_score_blob_on_update(monkeypatch, level, new_scores):
    import database.conversations as db
    import tests.unit.fixtures.strict_firestore_transaction as fixture

    store = fixture.StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s', text='before', speaker_id=1, is_user=False, start=0, end=6)
    store.rows[path] = db.encode_conversation_for_write(
        'u',
        dict(
            id='c',
            data_protection_level=level,
            transcript_segments=[segment],
            speaker_match_scores=[row()],
            other_metadata='x' * (898 * 1024),
        ),
        level,
    )
    assert scores.FIELD in store.rows[path]
    store.rows[path]['other_metadata'] = 'x' * (900 * 1024)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    update = dict(segment, text='after')
    if new_scores:
        update[scores.FIELD] = row(2)
    db.update_conversation_segments('u', 'c', [update])
    assert store.rows[path][scores.FIELD] is db.firestore.DELETE_FIELD
    # The strict fake retains sentinels; verify the real SDK expresses deletion.
    from google.cloud.firestore_v1 import _helpers

    writes = _helpers.pbs_for_update(
        'projects/test/databases/(default)/documents/c/c', {scores.FIELD: store.rows[path][scores.FIELD]}, None
    )
    assert scores.FIELD in writes[0].update_mask.field_paths
    assert scores.FIELD not in writes[0].update.fields
    assert db.prepare_conversation_for_read(store.rows[path], 'u')['transcript_segments'][0]['text'] == 'after'


@pytest.fixture
def score_merge_modules():
    import utils.conversations.merge_conversations as merge
    import utils.conversations.process_conversation
    import utils.notifications as notifications

    return merge, notifications


@pytest.mark.parametrize('malformed_donor', [False, True])
def test_manual_merge_retains_bounded_donor_scores(monkeypatch, score_merge_modules, malformed_donor):
    from datetime import timedelta

    merge, notifications = score_merge_modules
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    sources = {
        cid: dict(
            id=cid,
            created_at=now + timedelta(minutes=i),
            started_at=now + timedelta(minutes=i),
            finished_at=now + timedelta(minutes=i + 1),
            transcript_segments=[],
            source='omi',
            speaker_match_scores=[row(1, scope=cid)],
        )
        for i, cid in enumerate(['a', 'b'])
    }
    if malformed_donor:
        sources['b'][scores.FIELD] = [42]
    captured = []
    failures = []
    monkeypatch.setattr(merge.conversations_db, 'get_conversation', lambda uid, cid: sources[cid])
    monkeypatch.setattr(merge, '_collect_all_photos', lambda *a: [])
    monkeypatch.setattr(merge, '_copy_audio_chunks_for_merge', lambda *a: [])
    monkeypatch.setattr(
        merge.lifecycle_service, 'create_processing_conversation', lambda uid, data: captured.append(data)
    )
    monkeypatch.setattr(merge.lifecycle_service, 'complete', lambda *a: None)
    monkeypatch.setattr(merge, '_delete_conversation_and_related_data', lambda *a, **k: None)
    monkeypatch.setattr(merge, 'canonical_intake_is_fenced', lambda: False)
    monkeypatch.setattr(merge, 'record_capture_outcome', lambda *a: None)
    monkeypatch.setattr(merge, '_handle_merge_failure', lambda *a, **k: failures.append(a))
    monkeypatch.setattr(notifications, 'send_merge_completed_message', lambda *a: None)
    merge.perform_merge_async('u', ['a', 'b'], reprocess=False)
    assert len(captured) == 1 and failures == []
    if malformed_donor:
        assert scores.FIELD not in captured[0]
    else:
        assert {r['speaker_id_scope'] for r in captured[0][scores.FIELD]} == {'a', 'b'}


@pytest.fixture
def score_smart_world(monkeypatch):
    import tests.unit.test_conversation_smart_merge as fixture

    return fixture.world.__wrapped__(monkeypatch)


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('omit_scores', [False, True])
def test_smart_merge_transaction_retains_decoded_donor_scores(monkeypatch, score_smart_world, level, omit_scores):
    import database.conversations as db
    import database.smart_merge as smart_db
    import utils.conversations.smart_merge_policy as policy
    import tests.unit.test_conversation_smart_merge as fixture

    world = score_smart_world
    for cid, start in [('s', 0), ('d', 6)]:
        protection = 'enhanced' if cid == 'd' and omit_scores else level
        raw = world.add(cid, start, 4, speaker_match_scores=[row(1, scope=cid)], data_protection_level=protection)
        world.store.rows[fixture._path(cid)] = db.encode_conversation_for_write(fixture.UID, raw, protection)

    if omit_scores:
        monkeypatch.setattr(scores, 'aggregate', lambda *a: None)

    def plan(s, ss, d, ds, ancestors, last_fragment=None):
        update, tombstone = policy.absorb_payloads(s, ss, d, ds, merged_at=fixture.T0, decision={})
        return None, update, tombstone, {}

    result = smart_db.absorb_conversation(
        fixture.UID, 's', 'd', expected_revision=0, plan=plan, firestore_client=world.store
    )
    assert result.outcome == 'absorbed'
    decoded = db.prepare_conversation_for_read(world.raw('s'), fixture.UID)
    if omit_scores:
        if level == 'standard':
            assert world.raw('s')[scores.FIELD] is db.firestore.DELETE_FIELD
            assert scores.FIELD not in decoded
        else:
            assert {r['speaker_id_scope'] for r in decoded[scores.FIELD]} == {'s'}
    else:
        assert {r['speaker_id_scope'] for r in decoded[scores.FIELD]} == {'s', 'd'}
        assert isinstance(world.raw('s')[scores.FIELD], str if level == 'enhanced' else bytes)


def test_identity_cluster_score_aggregates_all_constituents():
    import utils.stt.conversation_speakers as resolver

    segments = [
        dict(id=f's{i}', speaker_id=i, speaker_id_scope=f'sync:{i}', start=i * 6, end=(i + 1) * 6, is_user=False)
        for i in range(4)
    ]
    embeddings = {f's{i}': np.array([1.0, 0.0]) if i < 2 else np.array([0.0, 1.0]) for i in range(4)}
    result = resolver.resolve_conversation_speakers(
        segments,
        embeddings,
        voiceprints={'p': np.array([0.8, 0.6])},
        embedding_seconds={f's{i}': 3.0 for i in range(4)},
    )
    assert len(set(result.speaker_ids.values())) == 1
    assert len(result.match_scores) == 1
    summary = result.match_scores[0]
    assert summary['merged_cluster_count'] == 2
    assert summary['evidence_seconds'] == 12.0
    assert summary['person_distance'] == 0.2
    assert summary['distance_aggregation'] == 'min_constituent_v1'
    assert summary['accepted_person_id'] == 'p'


def test_merge_score_union_preserves_unscoped_donor_keys_and_cap():
    union = scores.aggregate(
        [{'id': 'a', scores.FIELD: [row(1, 'resolution')]}, {'id': 'b', scores.FIELD: [row(1, 'resolution')]}]
    )
    assert len(union) == 2
    assert {r['speaker_id_scope'] for r in union} == {'conversation:a', 'conversation:b'}
    capped = scores.aggregate([{'id': str(i), scores.FIELD: [row(1, 'resolution')]} for i in range(30)])
    assert len(capped) == 16


@pytest.mark.parametrize('entry', ['constructor', 'model_validate', 'factory'])
@pytest.mark.parametrize('bad', [b'raw-compressed', 'raw-encrypted', {}, [None], [{'stage': 'capture'}], [42]])
def test_raw_scores_fail_open_at_every_model_entry(entry, bad):
    import models.conversation as models
    from utils.conversations.factory import deserialize_conversation

    payload = conversation().model_dump()
    payload[scores.FIELD] = bad
    if entry == 'constructor':
        restored = models.Conversation(**payload)
    elif entry == 'model_validate':
        restored = models.Conversation.model_validate(payload)
    else:
        restored = deserialize_conversation(payload)
    assert restored.id == 'c'
    assert restored.speaker_match_scores is None
    assert scores.FIELD not in restored.model_dump(mode='json')
    assert payload[scores.FIELD] == bad  # Never mutate the caller's stored document.


@pytest.fixture
def manual_score_routes(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import database.conversations as db
    import database.speaker_learning_jobs as learning_jobs
    import routers.conversations as assignment_router
    import routers.speaker_labels as rejection_router
    import utils.other.endpoints as auth
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    store = StrictFirestore()
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(db, 'db', store)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(db, 'record_speaker_review', lambda *a: None)
    monkeypatch.setattr(learning_jobs, 'record_speaker_learning_job_events', lambda *a: None)
    monkeypatch.setattr(assignment_router, '_emit_speaker_identity_confirmed', lambda **kw: None)
    app = FastAPI()
    app.include_router(assignment_router.router)
    app.include_router(rejection_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'u'
    return TestClient(app), store


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('operation', ['assignment', 'rejection'])
@pytest.mark.parametrize('corrupt', [False, True])
def test_manual_speaker_routes_with_stored_scores(manual_score_routes, monkeypatch, level, operation, corrupt):
    import database.conversations as db

    client, store = manual_score_routes
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s', text='synthetic', speaker_id=1, is_user=operation == 'rejection', start=0, end=6)
    data = conversation([segment], data_protection_level=level).model_dump()
    data[scores.FIELD] = [row()]
    store.rows[path] = db.encode_conversation_for_write('u', data, level)
    if corrupt:
        store.rows[path][scores.FIELD] = 'bad-encrypted' if level == 'enhanced' else b'bad-compressed'
    blob = store.rows[path][scores.FIELD]
    returned = []
    assign = db.assign_conversation_speaker

    def commit(*a, **kw):
        result = assign(*a, **kw)
        returned.append(result[0])
        return result

    monkeypatch.setattr(db, 'assign_conversation_speaker', commit)
    if operation == 'assignment':
        response = client.patch(
            '/v1/conversations/c/assign-speaker/1?assign_type=is_user&value=true&use_for_speech_training=false',
            json={'segment_ids': ['s'], 'assign_type': 'is_user', 'value': 'true'},
        )
    else:
        response = client.post('/v1/conversations/c/speakers/1/reject', json={'kind': 'not_me', 'segment_ids': ['s']})
    assert response.status_code == 200, response.text
    assert response.json()['transcript_segments'][0]['is_user'] == (operation == 'assignment')
    assert scores.FIELD not in response.json()
    assert store.rows[path][scores.FIELD] == blob
    assert returned[0].get(scores.FIELD) == (None if corrupt else [row()])
    receipt = db.decode_manual_speaker_assignments('u', store.rows[path]['manual_speaker_assignments'], True)
    assert receipt['generation'] == 1


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('operation', ['text', 'assignment', 'translation'])
def test_partial_transcript_writes_reclaim_stored_scores(manual_score_routes, level, operation):
    import database.conversations as db

    _, store = manual_score_routes
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s', text='synthetic', speaker_id=1, is_user=False, start=0, end=6)
    data = conversation([segment], data_protection_level=level).model_dump()
    data[scores.FIELD] = [row()]
    store.rows[path] = db.encode_conversation_for_write('u', data, level)
    assert scores.FIELD in store.rows[path]
    store.rows[path]['other_metadata'] = 'x' * (900 * 1024)
    if operation == 'text':
        assert db.update_conversation_segment_text('u', 'c', 's', 'edited') == 'ok'
    elif operation == 'assignment':
        updated, *_ = db.assign_conversation_speaker(
            'u', 'c', is_user=True, speaker_id=1, use_for_speech_training=False
        )
        assert scores.FIELD not in updated
    else:
        assert db.materialize_translation('u', 'c', 's', 'synthetic', 'en', 'translated', firestore_client=store)
    assert store.rows[path][scores.FIELD] is db.firestore.DELETE_FIELD
    readable = db.prepare_conversation_for_read(store.rows[path], 'u')
    assert scores.FIELD not in readable
    stored_segment = readable['transcript_segments'][0]
    if operation == 'text':
        assert stored_segment['text'] == 'edited'
    elif operation == 'assignment':
        assert stored_segment['is_user']
    else:
        assert stored_segment['translations'] == [{'lang': 'en', 'text': 'translated'}]


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('other_stages', [False, True])
def test_successful_resolution_without_comparisons_clears_stale_rows(monkeypatch, level, other_stages):
    import database.conversations as db
    import tests.unit.test_conversation_speaker_resolution_stage as fixture
    import utils.conversations.speaker_resolution as stage

    fixture.env.__wrapped__(monkeypatch)
    plan = [0, 1] * 4
    fixture._install_audio(monkeypatch, plan)
    conv = fixture._conversation(plan)
    old = [row(7, 'resolution')]
    retained = [row(1, 'capture'), row(2, 'sync')] if other_stages else []
    conv.speaker_match_scores = retained + old
    stage.resolve_speakers_for_processing('u1', conv)
    assert conv.speaker_resolution.status == 'resolved'
    assert conv.speaker_match_scores == retained
    # Processing merges against the current stored blob, so check persistence,
    # including an entirely empty score list, rather than just in-memory state.
    concurrent = [row(9, 'capture')] if other_stages else []
    existing = db.encode_conversation_for_write('u1', dict(speaker_match_scores=concurrent + old), level)
    existing['data_protection_level'] = level
    update = db.encode_conversation_for_write('u1', conv.model_dump(), level)
    assert scores.FIELD in update
    db._reapply_current_manual_assignments('u1', update, existing)
    decoded = db.prepare_conversation_for_read(update, 'u1')
    assert decoded[scores.FIELD] == concurrent + retained
    assert all(r['stage'] != 'resolution' for r in decoded[scores.FIELD])
    assert len(conv.transcript_segments) == len(plan)


def test_empty_processing_scores_preserve_resolution_without_resolution_state():
    current = [row(7, 'resolution')]
    assert scores.merge_processing(current, []) == current
    assert scores.merge_processing(current, [], replace_resolution=True) == []
