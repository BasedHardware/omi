"""Synthetic upload-label constraints and post-group identity decisions."""

import time

import numpy as np
import pytest

from config import batch_conversation_speakers as flags
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
