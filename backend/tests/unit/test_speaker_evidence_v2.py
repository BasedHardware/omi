"""Synthetic-only regressions for wave 2 speaker evidence."""

from types import SimpleNamespace
import uuid

import numpy as np
import pytest

from models.speaker_evidence import SpeakerEvidence
from utils.speakers import context, evidence, policy, processing
from utils.speakers.person_pool import pool_profile
from utils.speakers.refinement import pcm_energy
from utils.stt.conversation_speakers import Identity


@pytest.fixture(autouse=True)
def explicit_shadow_storage_sample(monkeypatch):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SHADOW_PERCENT', '100')


def segments(count):
    return [
        dict(
            id=f's{i}',
            speaker_id=1000 + i,
            speaker_id_scope='sync:fixture',
            start=i * 6,
            end=(i + 1) * 6,
            is_user=False,
            person_id=None,
        )
        for i in range(count)
    ]


def resolution(rows, vectors, distances=None, identities=None):
    return SimpleNamespace(
        speaker_ids={s['id']: s['speaker_id'] for s in rows},
        voice_centroids={s['speaker_id']: v for s, v in zip(rows, vectors)},
        voice_distances=distances or {},
        voice_identities=identities or {},
        voice_identity_statuses={},
        coverage=1,
    )


ROSTER = [{'name': 'Fixture A', 'person_id': 'p1'}, {'name': 'Fixture B', 'person_id': 'p2'}]


def test_234_clusters_merge_to_two_and_preserve_every_segment():
    rows = segments(234)
    result = evidence.build_evidence(
        rows, resolution(rows, [[1, 0] if i % 2 else [0, 1] for i in range(234)]), roster=ROSTER
    )
    assert len(result.clusters) == result.participant_count_hint == 2
    assert sorted(sid for c in result.clusters for sid in c.segment_ids) == sorted(s['id'] for s in rows)
    assert all(len(c.segment_ids) == 117 for c in result.clusters)
    assert result.owner_anchor == 'none'
    assert 'owner_unanchored' in result.abstentions
    assert SpeakerEvidence.model_validate_json(result.model_dump_json()) == result


def test_count_never_forces_distant_or_missing_vectors():
    rows = segments(6)
    for vectors in (np.eye(6), [None] * 6):
        result = evidence.build_evidence(rows, resolution(rows, vectors), roster=ROSTER)
        assert len(result.clusters) == 6
        assert 'participant_count_unresolved' in result.abstentions


def test_distinct_confident_people_and_manual_receipts_are_transitive_cannot_links():
    rows = segments(6)
    ids = {1000 + i: Identity(False, f'p{i%3}') for i in range(6)}
    result = evidence.build_evidence(
        rows, resolution(rows, [[1, 0]] * 6, {1000 + i: {f'p{i%3}': 0.01} for i in range(6)}, ids), roster=ROSTER
    )
    assert len(result.clusters) == 3
    assert 'participant_count_unresolved' in result.abstentions
    assert all(len({c.person_id for c in v.candidates if c.label_eligible}) == 1 for v in result.clusters)
    receipt = {'segments': {rows[i]['id']: {'person_id': f'p{i%3}', 'generation': 1} for i in range(6)}}
    manual = evidence.build_evidence(rows, resolution(rows, [[1, 0]] * 6), roster=ROSTER, receipt=receipt)
    assert len(manual.clusters) == 3
    assert {p for _, p in evidence.project_labels(manual, receipt).values()} == {'p0', 'p1', 'p2'}


def test_no_hint_does_not_reduce_voices():
    rows = segments(6)
    result = evidence.build_evidence(rows, resolution(rows, [[1, 0]] * 6))
    assert len(result.clusters) == 6
    assert result.participant_count_hint is None


def test_same_name_people_stay_competing_candidates():
    roster = [
        {'name': 'John', 'email': 'a@example.invalid', 'person_id': 'p1'},
        {'name': 'John', 'email': 'b@example.invalid', 'person_id': 'p2'},
    ]
    assert len(context.unique_roster(roster)) == 2
    rows = segments(1)
    result = evidence.build_evidence(rows, resolution(rows, [[1, 0]], {1000: {'p1': 0.4, 'p2': 0.42}}), roster=roster)
    assert evidence.project_labels(result, {}) == {}
    assert {c.person_id for c in result.clusters[0].candidates if c.source == 'roster'} == {'p1', 'p2'}
    assert not any(c.label_eligible for c in result.clusters[0].candidates)


def test_two_johns_can_be_distinct_voice_matches():
    rows = segments(2)
    result = evidence.build_evidence(
        rows,
        resolution(rows, np.eye(2), {1000: {'p1': 0.1, 'p2': 0.9}, 1001: {'p2': 0.1, 'p1': 0.9}}),
        roster=[{'name': 'John', 'person_id': 'p1'}, {'name': 'John', 'person_id': 'p2'}],
    )
    assert evidence.project_labels(result, {}) == {'s0': (False, 'p1'), 's1': (False, 'p2')}


@pytest.mark.parametrize('distance,accepted', [(0.499, True), (0.55, True), (0.649, True), (0.65, False), (0.8, False)])
def test_enrolled_person_uses_existing_live_calibration_at_finalize(distance, accepted):
    rows = segments(1)
    result = evidence.build_evidence(rows, resolution(rows, [[1, 0]], {1000: {'p1': distance, 'user': 1}}))
    assert (evidence.project_labels(result, {}).get('s0', (False, None))[1] == 'p1') == accepted


def test_owner_does_not_get_relaxed_person_threshold():
    rows = segments(1)
    result = evidence.build_evidence(rows, resolution(rows, [[1, 0]], {1000: {'user': 0.55}}))
    assert result.owner_anchor == 'none'
    assert evidence.project_labels(result, {}).get('s0', (False, None)) == (False, None)


@pytest.mark.parametrize('gap,allowed,expected', [(15, True, 'near_field'), (5, True, 'none'), (15, False, 'none')])
def test_near_field_requires_repeatable_energy_gap_and_wearer_source(gap, allowed, expected):
    rows = segments(6)
    for i, row in enumerate(rows):
        row['speaker_id'] = 1000 + i % 2
    resolved = resolution(rows, [[1, 0] if i % 2 else [0, 1] for i in range(6)])
    energies = {s['id']: -20 - (gap if i % 2 else 0) for i, s in enumerate(rows)}
    result = evidence.build_evidence(rows, resolved, energies=energies, near_field_allowed=allowed)
    assert result.owner_anchor == expected
    labels = evidence.project_labels(result, {})
    assert all(
        labels.get(s['id'], (False, None))[0] == (expected == 'near_field' and i % 2 == 0) for i, s in enumerate(rows)
    )


def test_missing_competing_audio_does_not_anchor_owner():
    rows = segments(2)
    result = evidence.build_evidence(rows, resolution(rows, np.eye(2)), energies={'s0': -10}, near_field_allowed=True)
    assert result.owner_anchor == 'none'


def test_desktop_channel_anchor_and_manual_rejection():
    rows = segments(2)
    result = evidence.build_evidence(rows, channel_ids=['s0'])
    assert result.owner_anchor == 'channel'
    assert evidence.project_labels(result, {}) == {'s0': (True, None)}
    receipt = {'segments': {'s0': {'is_user': False, 'person_id': 'p1', 'generation': 1}}}
    assert evidence.project_labels(result, receipt)['s0'] == (False, 'p1')


def test_pcm_energy_and_context_cache_metadata():
    pcm = (np.ones(16000) * 3276).astype('<i2').tobytes()
    assert pcm_energy(pcm) == pytest.approx(-20, abs=0.01)
    token = processing.begin()
    processing.capture_energy('s0', pcm)
    metadata = processing.energy_metadata()
    processing._current.reset(token)
    token = processing.begin()
    processing.restore_energy(metadata)
    assert processing.energy_metadata() == metadata
    processing._current.reset(token)


@pytest.mark.parametrize('mode,allowed', [('off', True), ('shadow', True), ('serve', False), ('typo', True)])
def test_name_only_gate_defaults_to_shadow(monkeypatch, mode, allowed):
    monkeypatch.setenv(evidence.FLAG, mode)
    monkeypatch.setenv(evidence.FLAG + '_SERVE_PERCENT', '0')
    monkeypatch.delenv(evidence.FLAG + '_SERVE_UID_SHA256S', raising=False)
    assert context.name_only_allowed(uuid.uuid4().hex) == allowed


def profile(vector, seconds=8):
    return dict(
        speaker_embedding=vector,
        speech_samples=['new.wav'],
        speech_sample_transcripts=[''],
        speech_sample_source={'conversation_id': 'new', 'segment_ids': ['s']},
        voice_speech_seconds=seconds,
    )


@pytest.mark.parametrize('vector', [[0, 0], [float('nan'), 1], [1e308, 1e308], [0, 1], [1, 0, 0]])
def test_bad_person_samples_cannot_replace_enrollment(vector):
    person = dict(speaker_embedding=[1, 0], speech_samples=['base.wav'], speech_samples_version=3)
    with pytest.raises(ValueError):
        pool_profile(person, profile(vector))
    assert person['speaker_embedding'] == [1, 0]


@pytest.mark.parametrize('seconds', [0, 2, float('nan'), float('inf')])
def test_short_or_invalid_sample_duration_rejected(seconds):
    with pytest.raises(ValueError, match='insufficient_person_voice_audio'):
        pool_profile({}, profile([1, 0], seconds))


def test_vector_magnitude_cannot_dominate_person_pool():
    person = dict(speaker_embedding=[1, 0], speech_samples=['base.wav'], speech_samples_version=3)
    result, _ = pool_profile(person, profile([800, 600]))
    expected = np.array([1.8, 0.6])
    expected /= np.linalg.norm(expected)
    assert np.allclose(result['speaker_embedding'], expected)


def test_count_cue_is_inclusive_and_cannot_lower_roster():
    cue = {'text': ' '.join(('just', 'two', 'of', 'us'))}
    assert context.participant_hint([], [cue]) == 2
    assert context.participant_hint([{'person_id': f'p{i}'} for i in range(4)], [cue]) == 4
    assert context.participant_hint([{'person_id': 'p1'}], []) == 2


@pytest.mark.parametrize('mode,expected', [('off', 234), ('shadow', 234), ('serve', 2)])
def test_234_to_two_at_processing_seam_preserves_shadow(monkeypatch, mode, expected):
    from models.transcript_segment import TranscriptSegment

    rows = segments(234)
    transcript = [TranscriptSegment(**row, text='') for row in rows]
    conversation = SimpleNamespace(
        id='fixture',
        transcript_segments=transcript,
        source='omi',
        speaker_resolution=SimpleNamespace(participant_speaker_ids=[]),
    )
    monkeypatch.setenv(evidence.FLAG, mode)
    monkeypatch.setenv(evidence.FLAG + '_SERVE_PERCENT', '0')
    monkeypatch.delenv(evidence.FLAG + '_SERVE_UID_SHA256S', raising=False)
    monkeypatch.setattr(processing, '_roster', lambda *args: ROSTER)
    stored = []
    monkeypatch.setattr(processing.storage, 'store_evidence', lambda *args, **kwargs: stored.append(args[2]))
    token = processing.begin(conversation)
    processing.capture_resolution(resolution(rows, [[1, 0] if i % 2 else [0, 1] for i in range(234)]))
    processing.reason('resolved')
    processing.finish(token, uuid.uuid4().hex, conversation, {})
    assert len({s.speaker_id for s in transcript}) == expected
    if mode == 'off':
        assert stored == []
    else:
        assert len(stored[-1].clusters) == 2


def test_channel_snapshot_survives_acoustic_resolution(monkeypatch):
    from models.transcript_segment import TranscriptSegment

    item = TranscriptSegment(id='s0', text='', speaker_id=0, start=0, end=8, is_user=True)
    conversation = SimpleNamespace(id='fixture', source='desktop', transcript_segments=[item])
    monkeypatch.setenv(evidence.FLAG, 'serve')
    monkeypatch.setattr(processing, '_roster', lambda *args: [])
    stored = []
    monkeypatch.setattr(processing.storage, 'store_evidence', lambda *args, **kwargs: stored.append(args[2]))
    token = processing.begin(conversation)
    item.is_user = False
    processing.finish(token, uuid.uuid4().hex, conversation, {})
    assert item.is_user
    assert item.speaker_identity_status == 'user'
    assert item.speaker_match_source == 'speaker_evidence_v2'
    assert item.speaker_label_source == 'auto'
    from utils.conversations.owner_attribution import confident_owner_segments

    assert confident_owner_segments([item]) == [item]
    assert stored[-1].owner_anchor == 'channel'


def test_near_field_does_not_override_distinct_person():
    rows = segments(6)
    for i, row in enumerate(rows):
        row['speaker_id'] = 1000 + i % 2
    resolved = resolution(
        rows, [[1, 0] if i % 2 else [0, 1] for i in range(6)], {1000: {'p1': 0.01}}, {1000: Identity(False, 'p1')}
    )
    result = evidence.build_evidence(
        rows,
        resolved,
        near_field_allowed=True,
        energies={r['id']: -15 if i % 2 == 0 else -35 for i, r in enumerate(rows)},
    )
    assert result.owner_anchor == 'none'
    assert not any(owner for owner, _ in evidence.project_labels(result, {}).values())


def test_surplus_merge_never_blends_desktop_mic_with_remote_channel():
    rows = segments(6)
    result = evidence.build_evidence(
        rows, resolution(rows, [[1, 0]] * 6), roster=ROSTER, channel_ids=['s0', 's1', 's2']
    )
    assert len(result.clusters) == 2
    assert result.owner_anchor == 'channel'
    labels = evidence.project_labels(result, {})
    assert [labels.get(s['id'], (False, None))[0] for s in rows] == [True, True, True, False, False, False]


def test_partial_resolution_does_not_publish_participant_list(monkeypatch):
    from models.transcript_segment import TranscriptSegment

    rows = segments(2)
    for row in rows:
        row['end'] = row['start'] + 20
    conversation = SimpleNamespace(
        id='fixture',
        source='omi',
        transcript_segments=[TranscriptSegment(**row, text='') for row in rows],
        speaker_resolution=SimpleNamespace(status='unavailable', participant_speaker_ids=[]),
    )
    partial = resolution(rows, np.eye(2))
    partial.coverage = 0.5
    monkeypatch.setenv(evidence.FLAG, 'serve')
    monkeypatch.setattr(processing, '_roster', lambda *args: ROSTER)
    monkeypatch.setattr(processing.storage, 'store_evidence', lambda *args, **kwargs: None)
    token = processing.begin(conversation)
    processing.capture_resolution(partial)
    processing.finish(token, uuid.uuid4().hex, conversation, {})
    assert conversation.speaker_resolution.participant_speaker_ids == []


def test_null_cluster_cannot_replace_numbered_speaker(monkeypatch):
    from models.transcript_segment import TranscriptSegment
    from models.speaker_evidence import VoiceCluster

    item = TranscriptSegment(id='s0', speaker_id=1, start=0, end=8, text='', is_user=False)
    conversation = SimpleNamespace(id='fixture', source='omi', transcript_segments=[item])
    proposed = SpeakerEvidence(
        status='resolved',
        policy_version='fixture',
        owner_anchor='none',
        clusters=[VoiceCluster(id='v0', speaker_id=None, segment_ids=['s0'])],
    )
    monkeypatch.setenv(evidence.FLAG, 'serve')
    monkeypatch.setattr(processing, 'build_evidence', lambda *a, **k: proposed)
    monkeypatch.setattr(processing, '_roster', lambda *a: [])
    monkeypatch.setattr(processing.storage, 'store_evidence', lambda *a, **k: None)
    token = processing.begin(conversation)
    processing.capture_resolution(SimpleNamespace(speaker_ids={'s0': 1}, coverage=1))
    processing.finish(token, uuid.uuid4().hex, conversation, {})
    assert item.speaker_id == 1
    assert item.speaker != 'SPEAKER_None'


def test_desktop_channel_split_is_not_a_count_reduction(monkeypatch, caplog):
    from models.transcript_segment import TranscriptSegment
    import logging

    rows = segments(2)
    for row in rows:
        row['speaker_id'] = 0
    transcript = [TranscriptSegment(**row, text='') for row in rows]
    transcript[0].is_user = True
    conversation = SimpleNamespace(id='fixture', source='desktop', transcript_segments=transcript)
    monkeypatch.setenv(evidence.FLAG, 'shadow')
    monkeypatch.setattr(processing, '_roster', lambda *a: ROSTER)
    monkeypatch.setattr(processing.storage, 'store_evidence', lambda *a, **k: None)
    with caplog.at_level(logging.INFO, logger=processing.__name__):
        token = processing.begin(conversation)
        processing.finish(token, uuid.uuid4().hex, conversation, {})
    assert 'check=participant_count outcome=agree' in caplog.text
    assert 'check=participant_count outcome=disagree' not in caplog.text


@pytest.mark.parametrize(
    'mode,sample,writes', [('off', '100', 0), ('shadow', '0', 0), ('shadow', '100', 1), ('serve', '0', 1)]
)
def test_evidence_shadow_writes_are_sampled(monkeypatch, mode, sample, writes):
    from models.transcript_segment import TranscriptSegment

    conversation = SimpleNamespace(
        id='fixture',
        source='omi',
        transcript_segments=[TranscriptSegment(id='s0', speaker_id=0, start=0, end=8, text='', is_user=False)],
    )
    monkeypatch.setenv(evidence.FLAG, mode)
    monkeypatch.setenv(evidence.FLAG + '_SERVE_PERCENT', '0')
    monkeypatch.delenv(evidence.FLAG + '_SERVE_UID_SHA256S', raising=False)
    monkeypatch.setenv(evidence.FLAG + '_SHADOW_PERCENT', sample)
    monkeypatch.setattr(processing, '_roster', lambda *a: [])
    stored = []
    monkeypatch.setattr(processing.storage, 'store_evidence', lambda *a, **k: stored.append(a))
    processing.finish(processing.begin(conversation), uuid.uuid4().hex, conversation, {})
    assert len(stored) == writes
