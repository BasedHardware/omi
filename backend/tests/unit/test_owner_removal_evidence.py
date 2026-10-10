"""Missing identity evidence must survive the real late resolver and encoded CAS."""

from copy import deepcopy
from datetime import timedelta

import numpy as np
import pytest

from models.transcript_segment import TranscriptSegment
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreSnapshot
from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    empty_manual_receipt,
    _capture_shifted_conversation,
    _install_audio,
    _span_flags,
    VOICES,
)
from tests.unit.test_owner_repair_committed import _commit_store, _counter
from utils.conversations import speaker_resolution as stage, speaker_grouping_shadow as shadow
from utils.manual_speaker_assignments import apply_manual_assignments
from utils.observability import owner_recognition as metrics
from utils.stt.conversation_speakers import resolve_conversation_speakers

MODES = ['incumbent', 'provider_strict', 'provider_cannot_link']
LABEL_FIELDS = ('is_user', 'person_id', 'speaker_identity_status', 'speaker_match_source', 'speaker_label_source')


def _owner(segment, source='conversation_voice'):
    segment.is_user = True
    segment.person_id = None
    segment.speaker_identity_status = 'user'
    segment.speaker_match_source = source
    segment.speaker_label_source = 'auto'


def _labels(segment):
    return {field: segment.get(field) for field in LABEL_FIELDS}


def _partial(monkeypatch, mode):
    _span_flags(monkeypatch)
    monkeypatch.setenv('SPEAKER_GROUPING_MODE', mode)
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW', 'off')
    _install_audio(monkeypatch, [0, 0, 1], offset=180.0)
    c = _capture_shifted_conversation([0, 0, 1])
    for s in c.transcript_segments[:2]:
        _owner(s)
        s.assign_resolved_speaker(s.speaker_id, 'conversation:c1')
    c.transcript_segments[-1].audio_capture_start = None
    c.transcript_segments[-1].audio_capture_end = None
    return c


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('missing', ['duration', 'prints'])
def test_partial_conversation_owner_survives_unknown_committed_pass(env, monkeypatch, mode, level, missing):
    cache, diarizer = env
    c = _partial(monkeypatch, mode)
    entries = {s.id: (s.end - s.start, VOICES[0]) for s in c.transcript_segments[:2]}
    seconds = None if missing == 'duration' else {sid: 3.8 for sid in entries}
    cache['c1'] = stage.encode_cache(entries, seconds)
    if missing == 'duration':
        monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: VOICES[0].tolist())
        diarizer.fail = True
    _, _, read = _commit_store(monkeypatch, c, level)
    before = [_labels(s) for s in read()['transcript_segments'][:2]]
    removed = _counter('owner_removed')
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    after = read()
    assert [_labels(s) for s in after['transcript_segments'][:2]] == before
    assert not after['transcript_segments'][-1]['is_user']
    assert after['speaker_resolution']['status'] == 'unavailable'
    assert _counter('owner_removed') == removed
    assert diarizer.calls == (2 if missing == 'duration' else 0)


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('source', ['live_embedding', 'conversation_voice'])
@pytest.mark.parametrize('owner_read', ['error', 'missing', 'invalid'])
@pytest.mark.parametrize('person_voice', [0, 1])
def test_unavailable_owner_with_paid_roster_preserves_existing_owner(
    env, monkeypatch, mode, level, source, owner_read, person_voice
):
    c = _partial(monkeypatch, mode)
    for s in c.transcript_segments[:2]:
        _owner(s, source)

    def load(uid):
        if owner_read == 'error':
            raise RuntimeError('synthetic owner read failure')
        return None if owner_read == 'missing' else [float('nan')]

    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', load)
    monkeypatch.setattr(
        stage.users_db,
        'get_people',
        lambda uid: [
            dict(
                id='p1',
                speaker_embedding=VOICES[person_voice].tolist(),
                speech_samples=['fake'],
                speech_samples_version=3,
            )
        ],
    )
    _, _, read = _commit_store(monkeypatch, c, level)
    before = [_labels(s) for s in read()['transcript_segments'][:2]]
    removed = _counter('owner_removed')
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    assert [_labels(s) for s in read()['transcript_segments'][:2]] == before
    assert _counter('owner_removed') == removed
    assert env[1].calls == 2


def _resolve_project(c, vectors, *, mode, prints, seconds=None, abstained=None, manual=None):
    result = resolve_conversation_speakers(
        c.transcript_segments,
        vectors,
        grouping=mode,
        provider_keys={s.id: shadow.provider_key(s) for s in c.transcript_segments},
        voiceprints=prints,
        embedding_seconds=seconds,
        abstained_segment_ids=abstained,
        manual_speakers=manual,
    )
    assert result is not None
    stage.apply_speaker_resolution(
        c,
        result.speaker_ids,
        result.voice_identities,
        result.voice_identity_statuses,
        owner_voiceprint_available=result.owner_voiceprint_available,
        contradicted_segment_ids=result.contradicted_segment_ids,
    )
    return result


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('person_voice', [0, 1])
def test_reduced_roster_preserves_entire_mixed_voice_without_labeling_unknown_members(
    env, monkeypatch, mode, level, person_voice
):
    _span_flags(monkeypatch)
    monkeypatch.setenv('SPEAKER_GROUPING_MODE', mode)
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW', 'off')
    _install_audio(monkeypatch, [0, 0, 0], offset=180.0)
    c = _capture_shifted_conversation([0, 0, 0])
    # Both transcript orders must preserve the same voice, including an
    # unlabeled member encountered before the accepted owner.
    _owner(c.transcript_segments[1], 'live_embedding')
    monkeypatch.setattr(
        stage.users_db,
        'get_people',
        lambda uid: [
            dict(
                id='p1',
                speaker_embedding=VOICES[person_voice].tolist(),
                speech_samples=['fake'],
                speech_samples_version=3,
            )
        ],
    )
    _, _, read = _commit_store(monkeypatch, c, level)
    before = [_labels(s) for s in read()['transcript_segments']]
    removed = _counter('owner_removed')
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    rows = read()['transcript_segments']
    assert len({s['speaker_id'] for s in rows}) == 1
    assert [_labels(s) for s in rows] == before
    assert _counter('owner_removed') == removed


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('existing_owner', [False, True])
def test_no_vote_short_live_owner_survives_without_promoting_unlabeled_fragment(mode, existing_owner):
    c = _capture_shifted_conversation([1, 0], seconds=8)
    short = c.transcript_segments[-1]
    short.end = short.start + 0.5
    if existing_owner:
        _owner(short, 'live_embedding')
    before = _labels(short.model_dump())
    result = _resolve_project(c, {'s0': VOICES[1]}, mode=mode, prints={'user': VOICES[0]}, seconds={'s0': 6})
    assert short.id not in result.speaker_ids
    assert (short.id in result.contradicted_segment_ids) is (not existing_owner)
    assert _labels(c.model_dump()['transcript_segments'][-1]) == before


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('decision', ['no_match', 'person', 'contention'])
def test_owner_inclusive_evidence_still_withdraws_automatic_owner(env, monkeypatch, mode, decision):
    c = _capture_shifted_conversation([1, 1], seconds=8)
    for s in c.transcript_segments:
        _owner(s, 'live_embedding')
    prints = {'user': VOICES[0]}
    vectors = {s.id: VOICES[1] for s in c.transcript_segments}
    if decision == 'person':
        prints['p1'] = VOICES[1]
    elif decision == 'contention':
        # Distinct voices both match the owner at .30, but neither wins .10.
        a = np.zeros(64)
        b = np.zeros(64)
        a[:2] = [0.7, np.sqrt(0.51)]
        b[:2] = [0.7, -np.sqrt(0.51)]
        vectors = {'s0': a, 's1': b}
    result = _resolve_project(c, vectors, mode=mode, prints=prints, seconds={s.id: 6 for s in c.transcript_segments})
    assert result.owner_voiceprint_available
    assert all(not s.is_user for s in c.transcript_segments)
    if decision == 'person':
        assert all(s.person_id == 'p1' for s in c.transcript_segments)
    else:
        assert all(
            s.speaker_identity_status == ('ambiguous' if decision == 'contention' else 'no_match')
            for s in c.transcript_segments
        )


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('votes', ['single', 'multiple', 'none', 'abstained'])
def test_unembedded_owner_uses_scoped_evidence_only(mode, votes):
    c = _capture_shifted_conversation([1, 2, 0], seconds=8)
    target = c.transcript_segments[-1]
    _owner(target, 'live_embedding')
    target.end = target.start + 0.5
    for s in c.transcript_segments:
        s.speaker_id_scope = 'live:one'
        s.speaker_id = 0
    if votes == 'none':
        target.speaker_id = 9
    abstained = {target.id} if votes == 'abstained' else set()
    # provider_strict must-links the provider voice; only the incumbent and
    # cannot-link mode can expose its internal acoustic contradiction.
    vectors = {'s0': VOICES[1], 's1': VOICES[2] if votes == 'multiple' else VOICES[1]}
    result = _resolve_project(
        c, vectors, mode=mode, prints={'user': VOICES[0]}, seconds={'s0': 6, 's1': 6}, abstained=abstained
    )
    assert target.is_user is (votes in ('none', 'abstained'))
    if votes == 'multiple' and mode != 'provider_strict':
        assert target.id in result.contradicted_segment_ids
    if votes in ('none', 'abstained'):
        assert target.id not in result.speaker_ids


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('refusal', ['coverage', 'no_vectors'])
def test_global_refusal_keeps_live_owner_but_retains_sync_conflict_policy(env, monkeypatch, level, refusal):
    _span_flags(monkeypatch)
    c = _capture_shifted_conversation([0, 0, 1])
    for s in c.transcript_segments[:2]:
        _owner(s, 'sync_embedding')
        s.speaker_id_scope = f'sync:{s.id}'
    _owner(c.transcript_segments[-1], 'live_embedding')
    if refusal == 'coverage':
        c.transcript_segments[0].audio_capture_end += 100
    else:
        monkeypatch.setattr(stage, '_embed_missing', lambda *a, **kw: (0, 'complete'))
    _install_audio(monkeypatch, [0, 0, 1], offset=180.0)
    _, _, read = _commit_store(monkeypatch, c, level)
    removed = _counter('owner_removed')
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    rows = read()['transcript_segments']
    assert [s['is_user'] for s in rows] == [False, False, True]
    assert all(s['speaker_identity_status'] == 'ambiguous' for s in rows[:2])
    assert _counter('owner_removed') == removed + 1


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('kind', ['speaker', 'segment'])
def test_manual_owner_receipt_survives_committed_renumbering_and_abstention(env, monkeypatch, mode, level, kind):
    c = _partial(monkeypatch, mode)
    for s in c.transcript_segments:
        s.is_user = False
        s.speaker_label_source = None
        s.speaker_match_source = None
    # The unplaceable tail has a stable excerpt override; the whole-voice case
    # exercises preserved numeric receipt authority on an embedded voice.
    receipt = (
        {'speakers': {'0': {'generation': 1, 'is_user': True}}}
        if kind == 'speaker'
        else {'segments': {'s2': {'generation': 1, 'is_user': True, 'segment_only': True}}}
    )
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda *a: receipt)
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: VOICES[1].tolist())
    _, _, read = _commit_store(monkeypatch, c, level, receipt=receipt)
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    target = read()['transcript_segments'][0 if kind == 'speaker' else 2]
    assert target['is_user'] and target['speaker_label_source'] == 'manual'
    assert target['speaker_match_source'] is None


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_concurrent_manual_edit_refuses_cas(env, monkeypatch, level):
    c = _partial(monkeypatch, 'incumbent')
    store, path, read = _commit_store(monkeypatch, c, level)
    candidate = read()
    edited = deepcopy(candidate)
    receipt = {
        'segments': {'s0': {'generation': 2, 'is_user': False, 'rejection': {'kind': 'not_me'}, 'segment_only': True}}
    }
    edited['manual_speaker_assignments'] = receipt
    edited['transcript_segments'] = apply_manual_assignments(edited['transcript_segments'], receipt)
    store.rows[path] = stage.conversations_db.encode_conversation_for_write('u1', edited, level)
    monkeypatch.setattr(StrictFirestoreSnapshot, 'update_time', property(lambda s: c.created_at + timedelta(seconds=1)))
    before = deepcopy(store.rows[path])
    removed = _counter('owner_removed')
    assert not stage.refresh_completed_speaker_identity('u1', 'c1', candidate=candidate)
    assert store.rows[path] == before
    assert _counter('owner_removed') == removed


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_newer_manual_negative_still_overrides_owner(env, monkeypatch, level):
    c = _partial(monkeypatch, 'incumbent')
    receipt = {
        'speakers': {'0': {'generation': 1, 'is_user': True}},
        'segments': {'s0': {'generation': 2, 'is_user': False, 'segment_only': True, 'rejection': {'kind': 'not_me'}}},
    }
    monkeypatch.setattr(stage.conversations_db, 'get_manual_speaker_receipt', lambda *a: receipt)
    _, _, read = _commit_store(monkeypatch, c, level, receipt=receipt)
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    assert not read()['transcript_segments'][0]['is_user']


@pytest.mark.parametrize(
    'change,expected', [('move', 'owner_added'), ('remove_subset', 'owner_removed'), ('regroup', 'identity_updated')]
)
def test_metric_keeps_segment_set_semantics(change, expected):
    before = {
        'id': 'c1',
        'transcript_segments': [
            TranscriptSegment(
                id=f's{i}', text='synthetic', start=i * 6, end=i * 6 + 6, speaker_id=i, is_user=i < 2
            ).model_dump()
            for i in range(3)
        ],
    }
    after = deepcopy(before)
    if change != 'regroup':
        after['transcript_segments'][0]['is_user'] = False
    if change == 'move':
        after['transcript_segments'][2]['is_user'] = True
    if change == 'regroup':
        after['transcript_segments'][0]['speaker_id'] = 9
    counts = {outcome: _counter(outcome) for outcome in ('owner_added', 'owner_removed', 'identity_updated')}
    metrics.record_owner_identity_repair(before, after)
    assert {outcome: _counter(outcome) - value for outcome, value in counts.items()} == {
        outcome: int(outcome == expected) for outcome in counts
    }
