"""Malformed text contributes neither audio evidence nor automatic identity."""

import math

import pytest

from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    empty_manual_receipt,
    _capture_shifted_conversation,
    _install_audio,
    _span_flags,
    VOICES,
)
from tests.unit.test_owner_repair_committed import _commit_store
from tests.unit.test_capture_window_resolution_r2 import verified_audio
from utils.conversations import speaker_resolution as stage
from utils.observability import owner_identity_retry as telemetry

BAD_WINDOWS = [
    (8.0, 8.0),
    (9.0, 8.0),
    (-1.0, 10.0),
    (float('nan'), 10.0),
    (8.0, float('nan')),
    (8.0, float('inf')),
    (float('-inf'), 10.0),
]


def _fixture(monkeypatch, window):
    _span_flags(monkeypatch)
    _install_audio(monkeypatch, [0, 0, 0], offset=180.0)
    conversation = _capture_shifted_conversation([0, 0, 0])
    for s in conversation.transcript_segments:
        s.speaker_id = 0
        s.speaker_id_scope = 'connection:shared'
    bad = conversation.transcript_segments[-1]
    bad.start, bad.end = window
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: VOICES[0].tolist())
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda uid: False)
    monkeypatch.setattr(stage.users_db, 'get_people', lambda uid: pytest.fail('free owner reads paid people'))
    return conversation, bad


@pytest.mark.parametrize('pass_name', ['first', 'late'])
@pytest.mark.parametrize('window', BAD_WINDOWS)
def test_mixed_invalid_text_applies_owner_without_labeling_bad_segment(env, monkeypatch, pass_name, window):
    conversation, bad = _fixture(monkeypatch, window)
    before = bad.model_dump(mode='python')
    located = []
    locate = stage.locate

    def track(*args, **kwargs):
        located.append(kwargs['segments'][0]['id'])
        return locate(*args, **kwargs)

    monkeypatch.setattr(stage, 'locate', track)
    finite_speech = math.isfinite(window[1] - window[0]) and window[1] - window[0] >= 1.0
    with telemetry.identity_pass(pass_name):
        assert stage.resolve_speakers_for_processing('u1', conversation)
        assert telemetry.resolver_trace().reason == ('partial' if finite_speech else 'resolved')
    assert conversation.speaker_resolution.status == ('unavailable' if finite_speech else 'resolved')
    assert all(s.is_user for s in conversation.transcript_segments[:-1])
    assert not bad.is_user
    assert bad.model_dump(mode='python') == before
    assert located == ['s0', 's1']
    assert env[1].calls == 2
    assert bad.id not in stage.decode_cache(env[0]['c1'])


@pytest.mark.parametrize(
    'window,reason',
    [
        ((-1.0, 10.0), 'invalid_text_window'),
        ((0.0, float('inf')), 'invalid_text_window'),
        ((0.0, 0.0), 'all_short'),
        ((1.0, 0.0), 'all_short'),
    ],
)
def test_all_invalid_keeps_existing_refusal(env, monkeypatch, window, reason):
    conversation, _ = _fixture(monkeypatch, window)
    for s in conversation.transcript_segments:
        s.start, s.end = window
    with telemetry.identity_pass('first'):
        assert stage.resolve_speakers_for_processing('u1', conversation)
        assert telemetry.resolver_trace().reason == reason
    assert conversation.speaker_resolution.status == ('capture' if reason == 'all_short' else 'unavailable')
    assert not any(s.is_user for s in conversation.transcript_segments)
    assert env[1].calls == 0


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('window', BAD_WINDOWS)
def test_late_compressed_encrypted_roundtrip_preserves_abstained_labels(env, monkeypatch, level, window):
    conversation, bad = _fixture(monkeypatch, window)
    bad.person_id = 'existing-person'
    bad.speaker_label_source = 'carried'
    store, path, read = _commit_store(monkeypatch, conversation, level)
    before = read()['transcript_segments'][-1]
    assert store.rows[path]['transcript_segments_compressed']
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    committed = read()
    after = committed['transcript_segments']
    finite_speech = math.isfinite(window[1] - window[0]) and window[1] - window[0] >= 1.0
    assert committed['speaker_resolution']['status'] == ('unavailable' if finite_speech else 'resolved')
    assert stage.completed_identity_retry_skip_reason(committed) == (
        None if finite_speech else 'already_resolved_owner'
    )
    assert all(s['is_user'] for s in after[:-1])
    for field in stage._IDENTITY_FIELDS:
        assert after[-1].get(field) == before.get(field)
    for field in ('start', 'end'):
        a, b = after[-1][field], before[field]
        assert a == b or (math.isnan(a) and math.isnan(b))
    assert env[1].calls == 2


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_negative_start_can_be_repaired_after_partial_owner_commit(env, monkeypatch, level):
    conversation, _ = _fixture(monkeypatch, (-1.0, 10.0))
    store, path, read = _commit_store(monkeypatch, conversation, level)
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    committed = read()
    assert committed['speaker_resolution']['status'] == 'unavailable'
    assert stage.completed_identity_retry_skip_reason(committed) is None
    assert all(s['is_user'] for s in committed['transcript_segments'][:-1])
    assert not committed['transcript_segments'][-1]['is_user']
    # Repair the raw window in the stored document, then run the actual late path.
    committed['transcript_segments'][-1].update(start=8.0, end=11.8)
    store.rows[path] = stage.conversations_db.encode_conversation_for_write('u1', committed, level)
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    repaired = read()
    assert repaired['speaker_resolution']['status'] == 'resolved'
    assert all(s['is_user'] for s in repaired['transcript_segments'])
    assert env[1].calls == 3


@pytest.mark.parametrize(
    'gate,reason',
    [
        ('ambiguity', 'global_manifest_ambiguity'),
        ('capture_hole', 'capture_coverage_hole'),
        ('spanless', 'manifest_unvalidated'),
    ],
)
def test_independent_global_gates_still_refuse(env, monkeypatch, gate, reason):
    conversation, bad = _fixture(monkeypatch, (8.0, 8.0))
    if gate == 'ambiguity':
        conversation.audio_files.append(conversation.audio_files[0].model_copy(deep=True))
    elif gate == 'capture_hole':
        bad.audio_capture_start += 1000
        bad.audio_capture_end += 1000
    else:
        conversation.audio_files[0].chunk_spans = []
    with telemetry.identity_pass('first'):
        stage.resolve_speakers_for_processing('u1', conversation)
        assert telemetry.resolver_trace().reason == reason
    assert not any(s.is_user for s in conversation.transcript_segments)
    assert env[1].calls == 0


@pytest.mark.parametrize('sentinel', [False, True])
def test_bad_text_cannot_use_cached_identity_or_change_verified_windows(env, monkeypatch, sentinel):
    conversation, bad = _fixture(monkeypatch, (-1.0, 10.0))
    if sentinel:
        bad.speaker_id = 99
    # A legacy cached owner vector is not permission to identify this window.
    env[0]['c1'] = stage.encode_cache({bad.id: (11.0, VOICES[0])}, {bad.id: 11.0})
    verified = stage._verified_read_session
    requests = []

    def track(uid, conv, files, pending, placements, deadline):
        requests.append((tuple(s.id for s in pending), dict(placements)))
        return verified(uid, conv, files, pending, placements, deadline)

    monkeypatch.setattr(stage, '_verified_read_session', track)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert all(s.is_user for s in conversation.transcript_segments[:-1])
    assert not bad.is_user
    assert requests[0][0] == ('s0', 's1')
    origin = conversation.started_at.timestamp() + 180.0
    assert [p.window for p in requests[0][1].values()] == [(origin, origin + 3.8), (origin + 4, origin + 7.8)]
    assert bad.id not in stage.decode_cache(env[0]['c1'])


def test_legacy_flag_off_still_abstains_invalid_cached_text(env, monkeypatch):
    conversation, bad = _fixture(monkeypatch, (-1.0, 10.0))
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
    for s in conversation.transcript_segments:
        s.speaker_id_scope = 'sync:one'
        s.audio_capture_start = s.audio_capture_end = None
    _install_audio(monkeypatch, [0, 0, 0])
    env[0]['c1'] = stage.encode_cache({bad.id: (11.0, VOICES[0])}, {bad.id: 11.0})
    stage.resolve_speakers_for_processing('u1', conversation)
    assert all(s.is_user for s in conversation.transcript_segments[:-1])
    assert not bad.is_user
    assert env[1].calls == 2
    assert bad.id not in stage.decode_cache(env[0]['c1'])


def test_shared_origin_collapse_is_still_a_global_refusal(env, monkeypatch):
    # Raw endpoints are ordered, but addition to the epoch rounds them together.
    conversation, bad = _fixture(monkeypatch, (1.0, math.nextafter(1.0, math.inf)))
    with telemetry.identity_pass('first'):
        stage.resolve_speakers_for_processing('u1', conversation)
        assert telemetry.resolver_trace().reason == 'invalid_text_window'
    assert not any(s.is_user for s in conversation.transcript_segments)
    assert env[1].calls == 0


def test_automatic_no_resolution_preserves_bad_labels_and_manual_authority(env, monkeypatch):
    conversation, bad = _fixture(monkeypatch, (8.0, 8.0))
    for i, s in enumerate(conversation.transcript_segments):
        s.speaker_id_scope = f'sync:{i}'
        s.is_user = True
        s.speaker_match_source = 'sync_embedding'
    before = {field: getattr(bad, field) for field in stage._IDENTITY_FIELDS}
    conversation.private_cloud_sync_enabled = False
    stage.resolve_speakers_for_processing('u1', conversation)
    assert {field: getattr(bad, field) for field in stage._IDENTITY_FIELDS} == before
    assert not any(s.is_user for s in conversation.transcript_segments[:-1])
    monkeypatch.setattr(
        stage.conversations_db,
        'get_manual_speaker_receipt',
        lambda *a: {'segments': {bad.id: {'generation': 1, 'is_user': False, 'person_id': 'manual-person'}}},
    )
    stage.resolve_speakers_for_processing('u1', conversation)
    assert not bad.is_user
    assert bad.person_id == 'manual-person'
    assert bad.speaker_label_source == 'manual'


@pytest.mark.parametrize('pass_name', ['first', 'late'])
def test_segment_counter_counts_segments_and_exit_counts_one_invocation(env, monkeypatch, pass_name):
    conversation, bad = _fixture(monkeypatch, (8.0, 8.0))
    other = bad.model_copy(deep=True)
    other.id = 'another-point'
    conversation.transcript_segments.append(other)

    def count(stage_name, reason):
        return telemetry.OWNER_IDENTITY_RETRY.labels(
            **{'pass': pass_name, 'stage': stage_name, 'reason': reason}
        )._value.get()

    before = count('segment_abstained', 'zero_text_window'), count('resolver_exit', 'resolved')
    with telemetry.identity_pass(pass_name):
        stage.resolve_speakers_for_processing('u1', conversation)
    assert count('segment_abstained', 'zero_text_window') - before[0] == 2
    assert count('resolver_exit', 'resolved') - before[1] == 1


@pytest.mark.parametrize('proof', ['valid', 'invalid_generation', 'wrong_decoded_extent'])
def test_real_inventory_proof_is_required_after_text_abstention(env, verified_audio, monkeypatch, proof):
    real_reader = stage._verified_read_session
    conversation, bad = _fixture(monkeypatch, (8.0, 8.0))
    # Exercise the production proof and PCM assembly, replacing only the
    # storage session with pinned in-memory chunks and the external diarizer.
    monkeypatch.setattr(stage, '_verified_read_session', real_reader)
    session = verified_audio(conversation, [(180.0, 192.0)])
    if proof == 'invalid_generation':
        session.chunks[0]['generation'] = 0
    elif proof == 'wrong_decoded_extent':
        path = session.chunks[0]['path']
        pcm, failure = session.cache[path]
        session.cache[path] = (pcm[:-3200], failure)
    with telemetry.identity_pass('first'):
        stage.resolve_speakers_for_processing('u1', conversation)
        assert (
            telemetry.resolver_trace().reason
            == {
                'valid': 'resolved',
                'invalid_generation': 'inventory_metadata_invalid',
                'wrong_decoded_extent': 'decoded_duration_mismatch',
            }[proof]
        )
    assert all(s.is_user for s in conversation.transcript_segments[:-1]) == (proof == 'valid')
    assert not bad.is_user
    assert env[1].calls == (2 if proof == 'valid' else 0)
