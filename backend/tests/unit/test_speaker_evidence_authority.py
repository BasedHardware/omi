"""Hermetic evidence, policy, projection, persistence and mode contracts."""

from types import SimpleNamespace
import uuid

import numpy as np
import pytest

from config import refactor_modes
from models.speaker_evidence import OWNER, SpeakerEvidence
from utils.speakers import evidence, policy, processing
from utils.stt.conversation_speakers import resolve_conversation_speakers
from utils.stt.speaker_match import select_speaker_match


def segment(sid, voice=0, scope='live:1', seconds=10):
    return dict(id=sid, speaker_id=voice, speaker_id_scope=scope, start=0, end=seconds, is_user=False, person_id=None)


@pytest.mark.parametrize(
    'point',
    [
        policy.LIVE,
        policy.FINALIZE,
        policy.CONTINUITY,
        policy.ONLINE_CLUSTER,
        policy.PARAKEET_CLUSTER,
        policy.BATCH_CLUSTER,
        policy.CONVERSATION_CLUSTER,
        policy.ABSORB,
    ],
)
@pytest.mark.parametrize('offset', [-1e-6, 0, 1e-6])
def test_operating_points_keep_old_strictness(point, offset):
    distance = point.distance + offset
    expected = distance <= point.distance if point.inclusive else distance < point.distance
    assert point.accepts(distance) == expected
    value = policy.probability(distance)
    boundary = policy.probability(point.distance)
    assert (value >= boundary if point.inclusive else value > boundary) == expected
    if not point.inclusive:
        assert select_speaker_match({'user': distance}, threshold=point.distance).accepted == expected


def test_table_monotonic_bounded_and_nonfinite_abstains():
    values = [policy.probability(d) for d in np.linspace(-0.1, 2.1, 1000)]
    assert values == sorted(values, reverse=True)
    assert all(0 <= v <= 1 for v in values)
    assert policy.probability(float('nan')) == 0
    assert policy.probability(float('inf')) == 0
    assert policy.band(policy.probability(0.5)) == 'likely'
    assert policy.band(policy.probability(0.65)) == 'unknown'


def test_multiscope_batch_candidates_owner_and_receipt_constraints():
    segments = [segment('a', 0), segment('b', 1, 'sync:2'), segment('c', 2, 'final:batch:3')]
    vectors = {'a': [1.0, 0.0, 0.0], 'b': [1.0, 0.0, 0.0], 'c': [0.0, 1.0, 0.0]}
    resolution = resolve_conversation_speakers(segments, vectors, voiceprints={'user': [1, 0, 0], 'p1': [0, 1, 0]})
    assert resolution is not None
    assert resolution.speaker_ids['a'] == resolution.speaker_ids['b']
    record = evidence.build_evidence(segments, resolution, roster=[{'name': 'Attendee'}])
    assert record.status == 'resolved'
    assert len(record.clusters) == 2
    assert all(any(c.person_id == OWNER for c in v.candidates) for v in record.clusters)
    assert all(
        v.candidates == sorted(v.candidates, key=lambda c: (-c.probability, c.source, c.person_id))
        for v in record.clusters
    )
    assert evidence.project_labels(record, {}) == {'a': (True, None), 'b': (True, None), 'c': (False, 'p1')}
    receipt = {'segments': {'a': {'generation': 2, 'is_user': False, 'person_id': 'p2', 'segment_only': True}}}
    assert evidence.project_labels(record, receipt)['a'] == (False, 'p2')
    assert evidence.project_labels(record, receipt)['b'] == (True, None)


def test_manual_excerpt_is_evidence_but_never_spreads_to_whole_voice():
    segments = [segment('a'), segment('b')]
    receipt = {'segments': {'a': {'generation': 1, 'is_user': True}}}
    record = evidence.build_evidence(segments, receipt=receipt)
    manual = next(c for c in record.clusters[0].candidates if c.source == 'manual')
    assert manual.probability == 1 and manual.band == 'confident'
    assert evidence.project_labels(record, receipt) == {'a': (True, None)}


def test_carried_scope_and_newer_negative_receipt_win():
    record = evidence.build_evidence([segment('a', 5, 'sync:new')])
    carried = {'speakers': {'5': {'is_user': True, 'source': 'carried', 'speaker_id_scope': 'sync:old'}}}
    assert evidence.project_labels(record, carried) == {}
    record = evidence.build_evidence([segment('a', 5)])
    receipt = {
        'speakers': {'5': {'is_user': True, 'generation': 1}},
        'segments': {'a': {'is_user': False, 'person_id': None, 'generation': 2, 'rejection': {'kind': 'not_me'}}},
    }
    assert evidence.project_labels(record, receipt)['a'] == (False, None)


def test_no_centroid_batch_abstains_without_poisoning_other_scope():
    segments = [segment('a'), segment('b', 3, 'final:batch:3')]
    resolution = resolve_conversation_speakers(
        segments, {'a': [1, 0]}, voiceprints={'user': [1, 0]}, abstained_segment_ids={'b'}
    )
    record = evidence.build_evidence(segments, resolution)
    assert record.status == 'partial'
    assert 'no_compatible_centroid' in record.abstentions
    assert evidence.project_labels(record, {}) == {'a': (True, None)}


@pytest.mark.parametrize(
    'mode,cohort,changed,runs',
    [
        ('off', False, False, False),
        ('shadow', False, False, True),
        ('shadow', True, True, True),
        ('serve', False, True, True),
        ('typo', False, False, True),
    ],
)
def test_processing_modes_preserve_shadow_and_persist_before_serving(monkeypatch, mode, cohort, changed, runs):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SHADOW_PERCENT', '100')
    account = str(uuid.uuid4())
    monkeypatch.setenv(evidence.FLAG, mode)
    monkeypatch.setenv(evidence.FLAG + '_SERVE_PERCENT', '100' if cohort else '0')
    monkeypatch.delenv(evidence.FLAG + '_SERVE_UID_SHA256S', raising=False)
    segments = [SimpleNamespace(**segment('a'))]
    conversation = SimpleNamespace(id='c', transcript_segments=segments, calendar_meeting_context=None)
    resolution = resolve_conversation_speakers(segments, {'a': [1, 0]}, voiceprints={'user': [1, 0]})
    stored = []

    def store(*args, **kwargs):
        assert not segments[0].is_user
        stored.append(args[2])

    monkeypatch.setattr(processing.storage, 'store_evidence', store)
    token = processing.begin()
    processing.capture_resolution(resolution)
    processing.reason('resolved')
    processing.finish(token, account, conversation, {})
    assert bool(stored) == runs
    assert segments[0].is_user == changed
    assert refactor_modes.mode(evidence.FLAG) == ('shadow' if mode == 'typo' else mode)


def test_storage_failure_preserves_labels(monkeypatch):
    monkeypatch.setenv(evidence.FLAG, 'serve')

    def fail(*args, **kwargs):
        raise RuntimeError('storage unavailable')

    monkeypatch.setattr(processing.storage, 'store_evidence', fail)
    segments = [SimpleNamespace(**segment('a'))]
    conversation = SimpleNamespace(id='c', transcript_segments=segments, calendar_meeting_context=None)
    token = processing.begin()
    processing.capture_resolution(resolve_conversation_speakers(segments, {'a': [1, 0]}, voiceprints={'user': [1, 0]}))
    processing.finish(token, str(uuid.uuid4()), conversation, {})
    assert not segments[0].is_user


def test_cluster_similarities_retained_above_floor():
    segments = [segment('a'), segment('b', 1)]
    resolution = SimpleNamespace(
        speaker_ids={'a': 0, 'b': 1},
        voice_distances={},
        voice_identities={},
        voice_identity_statuses={},
        voice_centroids={0: np.array([1.0, 0.0]), 1: np.array([0.5, np.sqrt(0.75)])},
        coverage=1,
    )
    record = evidence.build_evidence(segments, resolution)
    assert record.similarities[0].similarity == pytest.approx(0.5)
    assert SpeakerEvidence.model_validate_json(record.model_dump_json()) == record


@pytest.mark.parametrize('reprocess', [False, True])
def test_carried_manual_receipt_survives_resolution_and_storage_roundtrip(reprocess):
    from models.transcript_segment import TranscriptSegment
    from utils.stt.conversation_speakers import Identity

    item = TranscriptSegment(
        id='s',
        text='',
        is_user=False,
        start=0,
        end=10,
        speaker='SPEAKER_5',
        speaker_id=5,
        speaker_id_scope='sync:original',
    )
    receipt = {
        'speakers': {'5': {'generation': 1, 'is_user': True, 'source': 'carried', 'speaker_id_scope': 'sync:original'}}
    }
    resolved = resolve_conversation_speakers(
        [item], {'s': [1.0, 0.0]}, manual_speakers={5: Identity(is_user=True, person_id=None)}
    )
    item.assign_resolved_speaker(5, 'conversation:c')
    if reprocess:
        item = TranscriptSegment(**item.model_dump(mode='python'))
        item.assign_resolved_speaker(5, 'conversation:c')
    record = evidence.build_evidence([item], resolved, receipt=receipt)
    assert evidence.project_labels(record, receipt)['s'] == (True, None)
    assert any(c.source == 'manual' and c.probability == 1 for c in record.clusters[0].candidates)
    # A later selected-segment correction still wins against the carried scope.
    receipt['segments'] = {'s': {'generation': 2, 'is_user': False, 'person_id': 'p2'}}
    assert evidence.project_labels(record, receipt)['s'] == (False, 'p2')


def test_ambiguous_provider_scope_cannot_revive_stale_carried_receipt():
    item = {**segment('s', 5, 'conversation:c'), 'provider_speaker': {'id': -1, 'scope': 'sync:old'}}
    receipt = {'speakers': {'5': {'is_user': True, 'source': 'carried', 'speaker_id_scope': 'sync:old'}}}
    record = evidence.build_evidence([item], receipt=receipt)
    assert evidence.project_labels(record, receipt) == {}


def test_boundary_roster_reaches_evidence_as_prior_and_never_a_voice_label(monkeypatch):
    from models.boundary_evidence import BoundaryParticipant
    from utils.episodes import boundaries

    monkeypatch.setattr(
        boundaries, 'boundary_roster', lambda *args, **kwargs: [BoundaryParticipant(name='Fixture Attendee')]
    )
    candidates = processing._roster(uuid.uuid4().hex, SimpleNamespace(id='fixture', external_data={}))
    record = evidence.build_evidence([segment('a')], roster=candidates)
    roster = [candidate for voice in record.clusters for candidate in voice.candidates if candidate.source == 'roster']
    assert [candidate.name for candidate in roster] == ['Fixture Attendee']
    assert all(candidate.probability == policy.ROSTER_PRIOR and not candidate.label_eligible for candidate in roster)
    assert evidence.project_labels(record, {}) == {}


@pytest.mark.parametrize('identity', [(True, None, 'user'), (False, 'known', 'not_user')])
@pytest.mark.parametrize('reason', ['audio_expired', 'budget_hit', 'owner_print_deleted'])
def test_reprocessing_without_audio_preserves_established_labels_and_status(monkeypatch, identity, reason):
    monkeypatch.setenv(evidence.FLAG, 'serve')
    monkeypatch.setattr(processing.storage, 'store_evidence', lambda *a, **kw: None)
    monkeypatch.setattr(processing, '_roster', lambda *a: [])
    item = SimpleNamespace(
        **{**segment('established'), 'is_user': identity[0], 'person_id': identity[1]},
        speaker_identity_status=identity[2]
    )
    conversation = SimpleNamespace(id='synthetic', transcript_segments=[item])
    token = processing.begin()
    processing.reason(reason)
    processing.finish(token, str(uuid.uuid4()), conversation, {})
    assert (item.is_user, item.person_id, item.speaker_identity_status) == identity


def test_policy_operating_points_pin_legacy_literals_and_env_wiring(monkeypatch):
    import importlib.util
    from pathlib import Path

    names = {
        'FINALIZE': ('CONVERSATION_SPEAKER_VOICE_MATCH_THRESHOLD', 0.50),
        'ONLINE_CLUSTER': ('SPEAKER_CLUSTERING_THRESHOLD', 0.60),
        'PARAKEET_CLUSTER': ('PARAKEET_SPEAKER_CLUSTERING_THRESHOLD', 0.60),
        'BATCH_CLUSTER': ('PARAKEET_SPEAKER_AHC_THRESHOLD', 0.55),
        'CONVERSATION_CLUSTER': ('CONVERSATION_SPEAKER_AHC_THRESHOLD', 0.70),
        'ABSORB': ('CONVERSATION_SPEAKER_ABSORB_DISTANCE', 0.60),
    }

    def isolated():
        # A fresh module leaves the production singleton and other tests untouched.
        import sys

        name = 'speaker_policy_fixture_' + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(name, Path(policy.__file__))
        module = importlib.util.module_from_spec(spec)
        with monkeypatch.context() as patch:
            patch.setitem(sys.modules, name, module)
            spec.loader.exec_module(module)
        return module

    for env, _ in names.values():
        monkeypatch.delenv(env, raising=False)
    default = isolated()
    assert (default.LIVE.distance, default.CONTINUITY.distance, default.CROSS_SCOPE_CLUSTER.distance) == (
        0.65,
        0.35,
        0.60,
    )
    assert default.CROSS_EPOCH.distance == 0.50
    assert not default.LIVE.inclusive and not default.CONTINUITY.inclusive and not default.CROSS_SCOPE_CLUSTER.inclusive
    for name, (env, literal) in names.items():
        assert getattr(default, name).distance == literal
        assert getattr(default, name).inclusive == (name in {'BATCH_CLUSTER', 'CONVERSATION_CLUSTER'})
        with monkeypatch.context() as patch:
            patch.setenv(env, '.4321')
            changed = isolated()
            assert getattr(changed, name).distance == 0.4321
            if name == 'FINALIZE':
                assert changed.CROSS_EPOCH.distance == 0.4321
            for other, (_, original) in names.items():
                if other != name:
                    assert getattr(changed, other).distance == original


def test_malformed_stored_evidence_fails_open_without_content_or_identity_logs(monkeypatch, caplog):
    from database.read_boundary import MalformedDocError

    monkeypatch.setenv(evidence.FLAG, 'serve')

    def corrupt(*args):
        raise MalformedDocError(document_path='synthetic-private-payload', error_types=('bad',), error_fields=('bad',))

    monkeypatch.setattr(evidence.storage, 'get_evidence', corrupt)
    assert evidence.get_evidence('synthetic-private-owner', 'synthetic') is None
    assert 'speaker_evidence_read outcome=error' in caplog.text
    assert 'synthetic-private' not in caplog.text
