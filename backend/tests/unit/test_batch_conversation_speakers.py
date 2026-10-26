"""Synthetic upload-label constraints and post-group identity decisions."""

import time

import numpy as np
import pytest

from config import batch_conversation_speakers as flags
from config.batch_conversation_speakers import BATCH_CONVERSATION_SCOPE, has_batch_authority
from database import conversations as db
from models.conversation import Conversation
from tests.unit.test_conversation_speaker_resolution_stage import (
    STARTED,
    _conversation,
    _span_manifest,
    env,
)
from utils.conversations import speaker_resolution as stage
from utils.conversations.speaker_resolution_inputs import batch_provider_keys
from models.transcript_segment import TranscriptSegment
from utils.speakers.evidence import build_evidence, project_labels
from utils.stt.conversation_speakers import Identity, resolve_conversation_speakers


def rows(scopes, seconds=2.0):
    return [
        dict(id=f's{i}', speaker_id=i, speaker_id_scope=scope, start=i * seconds, end=(i + 1) * seconds)
        for i, scope in enumerate(scopes)
    ]


def resolve(segments, vectors, *, seconds=None, prints=None, manual=None, abstained=None, deadline=float('inf')):
    return resolve_conversation_speakers(
        segments,
        {s['id']: v for s, v in zip(segments, vectors) if v is not None},
        embedding_seconds=seconds if seconds is not None else {s['id']: s['end'] - s['start'] for s in segments},
        voiceprints=prints or {},
        manual_speakers=manual or {},
        abstained_segment_ids=abstained or set(),
        grouping='batch_authoritative',
        provider_keys={s['id']: (s['speaker_id_scope'], s.get('local', s['speaker_id'])) for s in segments},
        grouping_deadline=deadline,
    )


def test_same_speaker_across_four_short_uploads_pools_evidence_then_names():
    segments = rows([f'final:batch:unit{i}' for i in range(4)])
    result = resolve(segments, [[1, 0]] * 4, prints={'user': [1, 0]})
    assert result.coverage == 1
    assert len(set(result.speaker_ids.values())) == 1
    assert list(result.voice_identities.values()) == [Identity(True, None)]
    assert result.stats['batch_authoritative']


def test_local_label_stays_whole_even_with_noisy_segments_and_short_reply():
    segments = rows(['final:batch:a', 'final:batch:a', 'final:batch:a', 'final:batch:b'])
    for s in segments[:3]:
        s['local'] = 0
    segments[2]['end'] = segments[2]['start'] + 0.2
    result = resolve(segments, [[1, 0], [0, 1], None, [1, 1]])
    assert len(set(result.speaker_ids.values())) == 1
    assert 's2' not in result.contradicted_segment_ids


def test_same_unit_distinct_labels_cannot_link_through_other_units():
    segments = rows(['final:batch:a', 'final:batch:a', 'final:batch:b', 'final:batch:c'])
    result = resolve(segments, [[1, 0]] * 4)
    assert len(set(result.speaker_ids.values())) == 2
    assert result.speaker_ids['s0'] != result.speaker_ids['s1']


def test_matching_same_person_never_merges_acoustic_groups():
    segments = rows(['final:batch:a', 'final:batch:a'], seconds=8)
    result = resolve(segments, [[1, 0.4], [1, -0.4]], prints={'person': [1, 0]})
    assert result.speaker_ids['s0'] != result.speaker_ids['s1']
    assert list(result.voice_identities.values()) == [Identity(False, 'person')] * 2


def test_owner_contention_abstains_instead_of_merging_same_unit_voices():
    segments = rows(['final:batch:a', 'final:batch:a'], seconds=8)
    result = resolve(segments, [[1, 0.4], [1, -0.4]], prints={'user': [1, 0]})
    assert len(set(result.speaker_ids.values())) == 2
    assert not result.voice_identities
    assert set(result.voice_identity_statuses.values()) == {'ambiguous'}


def test_manual_owner_reserves_identity_and_receipt_id():
    segments = rows(['final:batch:a', 'final:batch:a'], seconds=8)
    result = resolve(segments, [[1, 0.4], [1, -0.4]], prints={'user': [1, 0]}, manual={0: Identity(True, None)})
    assert result.speaker_ids['s0'] == 0
    assert result.speaker_ids['s1'] != 0
    assert not result.voice_identities


def test_missing_measured_evidence_and_gaps_cannot_name_or_borrow_owner():
    segments = rows(['final:batch:a', 'final:batch:b', 'final:batch:c'], seconds=8)
    result = resolve(
        segments, [[1, 0]] * 3, seconds={'s0': 8, 's1': 0, 's2': 8}, prints={'user': [1, 0]}, abstained={'s2'}
    )
    assert result.speaker_ids == {'s0': 0, 's1': 1}
    assert 's2' not in result.speaker_ids
    assert result.voice_identities[0].is_user


def test_incompatible_profile_dimensions_do_not_prevent_anonymous_grouping():
    segments = rows(['final:batch:a', 'final:batch:b'], seconds=8)
    result = resolve(segments, [[1, 0]] * 2, prints={'user': [1, 0, 0]})
    assert len(set(result.speaker_ids.values())) == 1
    assert not result.voice_identities
    assert set(result.voice_identity_statuses.values()) == {'unknown'}


def test_batch_limit_is_groups_not_sentence_count_and_deadline_is_bounded():
    segments = rows(['final:batch:a'] * 300)
    for s in segments:
        s['local'] = 0
    assert len(set(resolve(segments, [[1, 0]] * 300).speaker_ids.values())) == 1
    with pytest.raises(TimeoutError):
        resolve(segments, [[1, 0]] * 300, deadline=time.monotonic() - 1)
    # 99 is the reserved Omi voice, so 1,026 rows contain 1,025 eligible groups.
    too_many = rows([f'final:batch:{i}' for i in range(1026)])
    with pytest.raises(ValueError, match='input limit'):
        resolve(too_many, [[1, 0]] * len(too_many))


def test_evidence_roster_cannot_merge_batch_groups_or_relax_name_matcher():
    segments = rows(['final:batch:a'] * 6, seconds=8)
    result = resolve(segments, [[1, 0]] * 6)
    assert len(set(result.speaker_ids.values())) == 6
    for voice in result.voice_centroids:
        result.voice_distances[voice] = {'person': 0.55}
    evidence = build_evidence(segments, result, roster=[{'name': 'Synthetic', 'person_id': 'person'}])
    assert len(evidence.clusters) == 6
    assert project_labels(evidence, {}) == {}


def test_kill_switch_defaults_on_only_with_persisted_batch_authority(monkeypatch):
    monkeypatch.delenv('BATCH_CONVERSATION_SPEAKERS_ENABLED', raising=False)
    segment = TranscriptSegment(
        id='s', text='synthetic', start=0, end=8, speaker_id=0, speaker_id_scope='final:batch:a', is_user=False
    )
    assert flags.enabled([segment])
    segment.assign_resolved_speaker(1, 'conversation:synthetic')
    assert flags.enabled([segment])
    monkeypatch.setenv('BATCH_CONVERSATION_SPEAKERS_ENABLED', 'false')
    assert not flags.enabled([segment])
    segment.provider_speaker = None
    assert not flags.has_batch_authority([segment])


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('evidence_mode', ['off', 'serve'])
def test_long_batch_storage_roundtrip_retains_partition_and_accepts_new_units(monkeypatch, env, level, evidence_mode):
    from utils.speakers import processing as evidence_processing

    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', evidence_mode)
    monkeypatch.delenv('BATCH_CONVERSATION_SPEAKERS_ENABLED', raising=False)
    monkeypatch.setattr(evidence_processing, '_roster', lambda *_: [])
    monkeypatch.setattr(evidence_processing.storage, 'store_evidence', lambda *a, **kw: None)
    monkeypatch.setattr(stage, 'load_voiceprints_for_resolution', lambda *a, **kw: {})
    store, diarizer = env
    conv = _conversation([0, 1] * 150, seconds=2, scopes=[f'final:batch:unit{i // 75}' for i in range(300)])
    for i, segment in enumerate(conv.transcript_segments):
        segment.speaker_id = (i // 75) * 2 + i % 2
    origin = STARTED.timestamp()
    conv.audio_files = [_span_manifest(origin, [(origin, origin + 604)])]
    vectors = {s.id: (1.8, np.array([1, 0.1 if i % 2 else -0.1])) for i, s in enumerate(conv.transcript_segments)}
    store['c1'] = stage.encode_cache(vectors, {sid: 1.8 for sid in vectors})
    assert stage.resolve_speakers_for_processing('synthetic', conv)
    before = [s.speaker_id for s in conv.transcript_segments]
    assert len(set(before)) == 2
    assert all(s.speaker_id_scope == f'{BATCH_CONVERSATION_SCOPE}c1' for s in conv.transcript_segments)

    stored = db.encode_conversation_for_write('synthetic', conv.model_dump(), level)
    rows = db.decode_transcript_segments_verified('synthetic', stored['transcript_segments'], True)
    assert all('provider_speaker' not in s for s in rows)  # >256 sidecars are deliberately dropped.
    conv = Conversation(**{**conv.model_dump(), 'transcript_segments': rows})
    assert has_batch_authority(conv.transcript_segments)
    # Even wildly inconsistent cached clips cannot split a prior must-link;
    # identical clips across prior voices cannot collapse their cannot-link.
    vectors = {s.id: (1.8, np.array([1, i % 3 - 1])) for i, s in enumerate(conv.transcript_segments)}
    store['c1'] = stage.encode_cache(vectors, {sid: 1.8 for sid in vectors})
    assert stage.resolve_speakers_for_processing('synthetic', conv)
    after = [s.speaker_id for s in conv.transcript_segments]
    assert len(set(after)) == 2
    assert all((before[i] == before[0]) == (after[i] == after[0]) for i in range(300))

    # A fresh upload can join a frozen group without joining the two old groups.
    fresh = TranscriptSegment(
        id='fresh',
        text='synthetic',
        start=600,
        end=601.8,
        speaker_id=8,
        speaker_id_scope='final:batch:fresh',
        is_user=False,
    )
    conv.transcript_segments.append(fresh)
    vectors['fresh'] = (1.8, np.array([1, 0]))
    store['c1'] = stage.encode_cache(vectors, {sid: 1.8 for sid in vectors})
    assert stage.resolve_speakers_for_processing('synthetic', conv)
    assert len({s.speaker_id for s in conv.transcript_segments}) == 2
    assert diarizer.calls == 0


def test_partial_marker_loss_uses_whole_snapshot_and_invalid_marker_abstains():
    segments = _conversation([0] * 4, scopes=[f'{BATCH_CONVERSATION_SCOPE}c1'] * 4).transcript_segments
    for s, voice in zip(segments, [0, 0, 1, 1]):
        s.speaker_id = voice
        s.provider_speaker = {'scope': f'final:batch:unit{s.id}', 'id': 0}
    segments[0].provider_speaker = None
    segments[3].provider_speaker = {'scope': 'ambiguous', 'id': -1}
    keys = batch_provider_keys(segments)
    assert keys['s0'] == keys['s1']
    assert keys['s0'] != keys['s2']
    assert 's3' not in keys
    result = resolve_conversation_speakers(
        segments,
        {s.id: [1, 0] for s in segments},
        grouping='batch_authoritative',
        provider_keys=keys,
        abstained_segment_ids={'s3'},
    )
    assert result.speaker_ids['s0'] == result.speaker_ids['s1']
    assert result.speaker_ids['s0'] != result.speaker_ids['s2']
    assert 's3' not in result.speaker_ids
