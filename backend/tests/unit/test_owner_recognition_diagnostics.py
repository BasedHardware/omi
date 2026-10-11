"""Execute live admission/matching and diagnostic-only persistence without cloud credentials."""

import asyncio
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

import config.owner_recognition_diagnostics as contract
from database import conversations as db
from models.conversation import Conversation
from routers.listen import speakers, transcripts
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_speaker_match import _live_matcher, _segment
from tests.unit.test_owner_speaker_profiles import _Persistence
from tests.unit.test_speaker_match_scores import conversation, row as score_row
from utils.observability import owner_recognition_diagnostics as observation


def live(monkeypatch, vectors):
    matcher, host, emitted = _live_matcher(monkeypatch, vectors)
    host.request.uid = 'diagnostic-user'
    host.state.speaker_id_enabled = True
    host.state.current_conversation_id = 'c'

    async def receipt(*args, **kwargs):
        return {}

    host.persistence = SimpleNamespace(call=receipt)
    host.session_id = 'socket-1'
    host.recording_session_id = 'recording-1'
    matcher._profile_conversation_id = 'c'
    matcher.diagnostics.begin('c', matcher._generation)
    return matcher, host, emitted


def snapshot(matcher):
    return matcher.diagnostics.snapshot('c')['live'][0]


@pytest.mark.parametrize('fragmented', [False, True])
def test_clean_65_second_single_owner_is_compared_and_diagnostics_are_attributable(monkeypatch, caplog, fragmented):
    monkeypatch.setenv('SPEAKER_MATCH_SCORES_ENABLED', 'true')
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = live(monkeypatch, [owner] * 12)
    matcher.person_embeddings.pop('p1')
    caplog.set_level('INFO')

    async def capture():
        for index in range(130 if fragmented else 1):
            segment = _segment(f's{index}', index * 0.5, 0.5 if fragmented else 65.0)
            segment['speaker_id_scope'] = 'socket:0'
            await matcher.match(1, segment)

    asyncio.run(capture())
    assert matcher.speaker_to_person[1][0] == 'user'
    summary = snapshot(matcher)
    assert summary['owner_comparisons'] >= 1
    assert summary['successful'] == summary['attempted'] <= speakers.MAX_VOICE_EMBEDDING_ATTEMPTS
    assert summary['pcm_seconds'] >= 5
    assert summary['scores_generated'] >= 1
    assert 'uid=diagnostic-user' in caplog.text and 'conversation=c' in caplog.text
    assert 'socket=socket-1' in caplog.text and 'scope=socket:0' in caplog.text
    assert 'The User' not in caplog.text
    store = StrictFirestore()
    path = ('users', 'diagnostic-user', 'conversations', 'c')
    stored_segment = dict(
        id='stored', text='synthetic', speaker_id=1, speaker_id_scope='socket:0', start=0, end=65, is_user=False
    )
    store.rows[path] = dict(id='c', transcript_segments=[stored_segment], data_protection_level='standard')
    assert db.update_conversation_segments(
        'diagnostic-user',
        'c',
        [dict(stored_segment, is_user=True, speaker_match_scores=matcher.match_scores[0])],
        firestore_client=store,
        segment_update_fields=('is_user',),
        owner_recognition_diagnostics=matcher.diagnostics.snapshot('c'),
    )
    persisted = db.prepare_conversation_for_read(store.rows[path], 'diagnostic-user')
    assert persisted['speaker_match_scores']
    assert persisted[contract.FIELD]['live'][0]['scores'] == 'present'


def test_no_print_refusal_then_profile_recovery_does_not_replay_or_change_admission(monkeypatch):
    matcher, host, _ = live(monkeypatch, [])
    host.speakers = matcher
    processor = transcripts.TranscriptProcessor.__new__(transcripts.TranscriptProcessor)
    processor.host, processor.suggested_segments = host, set()
    raw = dict(id='s', speaker_id=1, speaker_id_scope='socket:0', start=0, end=65, is_user=False)
    matcher.person_embeddings.clear()
    processor._queue_raw_detections([raw], None, 0)
    assert matcher.queue.empty() and snapshot(matcher)['reasons']['no_prints'] == 1
    matcher.person_embeddings['user'] = {'embedding': np.ones((1, 2)), 'name': 'Owner'}
    matcher.diagnostics.observe('profile_loaded')
    assert matcher.queue.empty()  # Diagnostics add no retries/replay.
    processor._queue_raw_detections([dict(raw, id='new')], None, 0)
    assert matcher.queue.qsize() == 1 and snapshot(matcher)['enqueued'] == 1


@pytest.mark.parametrize('reason', ['unplaced', 'queue_full', 'already_labeled', 'already_mapped'])
def test_admission_refusals_and_repeated_logs_are_bounded(monkeypatch, caplog, reason):
    matcher, host, _ = live(monkeypatch, [])
    host.speakers = matcher
    processor = transcripts.TranscriptProcessor.__new__(transcripts.TranscriptProcessor)
    processor.host, processor.suggested_segments = host, set()
    raw = dict(id='s', speaker_id=1, speaker_id_scope='socket:0', start=0, end=65, is_user=False)
    if reason == 'unplaced':
        raw['audio_alignment'] = 'unplaced'
    if reason == 'already_labeled':
        raw['is_user'] = True
    if reason == 'already_mapped':
        matcher.speaker_to_person[1] = ('user', 'Owner')
    if reason == 'queue_full':
        monkeypatch.setattr(matcher.queue, 'put_nowait', lambda value: (_ for _ in ()).throw(asyncio.QueueFull()))
    caplog.set_level('INFO')
    for _ in range(100):
        processor._queue_raw_detections([raw], None, 0)
    assert snapshot(matcher)['reasons'][reason] == 100
    assert sum(record.name == observation.__name__ for record in caplog.records) == 1
    assert snapshot(matcher).get('attempted', 0) == 0


@pytest.mark.parametrize('cap', ['voice', 'socket', 'both'])
def test_budget_observation_reuses_existing_first_block_and_counters(monkeypatch, caplog, cap):
    matcher, _, _ = live(monkeypatch, [])
    matcher._admit_voice(1)
    matcher._embedding_attempts[1] = speakers.MAX_VOICE_EMBEDDING_ATTEMPTS if cap != 'socket' else 0
    matcher._socket_embedding_tokens = 0 if cap != 'voice' else 16
    monkeypatch.setattr(speakers.time, 'monotonic', lambda: matcher._socket_embedding_refilled_at)
    caplog.set_level('INFO')
    for _ in range(100):
        assert not matcher._reserve_embedding(1, segment={'speaker_id_scope': 'socket:0'})
    assert snapshot(matcher)['reasons']['embedding_budget'] == 100
    assert snapshot(matcher)[f'budget_{cap}'] == 100
    assert caplog.text.count('speaker_id_budget_first_block') == 1
    assert f'cap={cap}' in caplog.text
    assert not any(record.name == observation.__name__ for record in caplog.records)


def test_failed_extraction_spends_budget_and_short_pcm_does_not(monkeypatch):
    matcher, host, _ = live(monkeypatch, [])
    monkeypatch.setattr(
        speakers, 'extract_embedding_from_bytes', lambda *args: (_ for _ in ()).throw(ValueError('synthetic'))
    )
    asyncio.run(matcher.match(1, _segment('s', 0, 5)))
    assert snapshot(matcher)['attempted'] == snapshot(matcher)['failed'] == 1
    assert matcher._embedding_attempts[1] == 1 and not matcher.speaker_to_person
    tokens = matcher._socket_embedding_tokens
    asyncio.run(matcher.match(2, _segment('tiny', 10, 0.5)))
    assert snapshot(matcher)['reasons']['window_shorter_than_minimum'] == 1
    assert matcher._socket_embedding_tokens == tokens


def test_finalize_snapshot_with_queue_and_no_tasks_does_not_claim_comparison(monkeypatch, caplog):
    matcher, _, _ = live(monkeypatch, [])
    matcher.queue.put_nowait(dict(_segment('s', 0, 5), speaker_id=1, conversation_id='c'))
    caplog.set_level('INFO')
    for _ in range(20):
        diagnostic = matcher.diagnostics.checkpoint('c', matcher.queue, matcher.tasks)
    summary = diagnostic['live'][0]
    assert summary['pending_queue'] == 1 and summary['pending_tasks'] == 0
    assert summary.get('comparisons', 0) == 0 and matcher.queue.qsize() == 1
    assert caplog.text.count('kind=live_stop') == 1


def test_generation_stop_freezes_inflight_metadata_and_does_not_paint_successor(monkeypatch):
    matcher, _, _ = live(monkeypatch, [])
    started, release = asyncio.Event(), asyncio.Event()
    old = matcher.diagnostics.current

    @observation.observe_query
    async def query(self, pcm):
        started.set()
        await release.wait()
        return np.ones((1, 2))

    monkeypatch.setattr(matcher, '_extract_query', query.__get__(matcher))

    async def run():
        task = asyncio.create_task(matcher.match(1, _segment('s', 0, 5)))
        await started.wait()
        matcher.clear()
        frozen = copy.deepcopy(old.data)
        matcher._profile_conversation_id = 'next'
        matcher.diagnostics.begin('next', matcher._generation)
        release.set()
        await task
        assert old.data == frozen
        assert matcher.diagnostics.snapshot('next')['live'][0].get('successful', 0) == 0
        assert not matcher.speaker_to_person

    asyncio.run(run())


def test_stop_is_once_with_pending_tasks_and_logging_failure_is_observational(monkeypatch):
    matcher, _, _ = live(monkeypatch, [])
    monkeypatch.setattr(observation.logger, 'info', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('sink')))
    matcher.diagnostics.observe('no_pcm')
    matcher.diagnostics.stop('drain', matcher.queue, {object()})
    frozen = copy.deepcopy(snapshot(matcher))
    matcher.diagnostics.stop('rollover', matcher.queue, set())
    matcher.diagnostics.observe('comparison')
    assert snapshot(matcher) == frozen and frozen['pending_tasks'] == 1


def test_contract_strips_content_limits_size_and_preserves_monotonic_first_summary():
    bad = {
        'text': 'PRIVATE_TRANSCRIPT_SENTINEL',
        'pcm': b'a',
        'embedding': [1, 2],
        'reason': {},
        'counts': {'secret': 'x'},
        'elapsed_seconds': float('nan'),
    }
    generations = [
        dict(
            bad,
            socket=f's{i}',
            conversation='c',
            generation=i,
            sequence=2,
            scopes=['x' * 999] * 99,
            reasons={r: 99 for r in contract.REASONS},
        )
        for i in range(10)
    ]
    value = contract.normalize({'live': generations, 'first_resolver': dict(bad, reason='private_cloud_disabled')})
    assert len(json.dumps(value, separators=(',', ':')).encode()) <= contract.MAX_BYTES
    assert len(value['live']) <= 4
    assert 'PRIVATE_TRANSCRIPT_SENTINEL' not in json.dumps(value)
    assert all(len(r['scopes']) <= 8 for r in value['live'])
    current = {
        'live': [dict(socket='s', conversation='c', sequence=5, attempted=5)],
        'first_resolver': {'reason': 'resolved'},
    }
    merged = contract.merge(
        current,
        {
            'live': [dict(socket='s', conversation='c', sequence=1, attempted=1)],
            'first_resolver': {'reason': 'no_vectors'},
        },
    )
    assert merged['live'][0]['attempted'] == 5 and merged['first_resolver']['reason'] == 'resolved'


def test_internal_field_has_python_storage_roundtrip_but_no_json_schema_or_client_payload():
    diagnostic = {'first_resolver': {'reason': 'endpoint_unconfigured'}}
    conv = conversation(owner_recognition_diagnostics=diagnostic)
    assert conv.model_dump()[contract.FIELD]['first_resolver']['reason'] == 'endpoint_unconfigured'
    assert contract.FIELD not in conv.model_dump(mode='json')
    assert contract.FIELD not in Conversation.model_json_schema()['properties']
    assert contract.FIELD not in conv.model_dump(exclude={contract.FIELD})


def test_metadata_only_flush_and_identity_flush_merge_current_diagnostics_without_changing_labels(monkeypatch):
    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s', text='synthetic', speaker_id=1, is_user=False, start=0, end=6)
    store.rows[path] = dict(
        id='c',
        transcript_segments=[segment],
        data_protection_level='standard',
        owner_recognition_diagnostics={'first_resolver': {'reason': 'private_cloud_disabled'}},
    )
    live_data = {'live': [dict(socket='s', conversation='c', generation=1, sequence=3, attempted=1)]}
    assert db.update_owner_recognition_diagnostics('u', 'c', live_data, firestore_client=store)
    assert store.rows[path]['transcript_segments'] == [segment]
    assert db.update_conversation_segments(
        'u',
        'c',
        [dict(segment, is_user=True, speaker_match_scores=score_row())],
        firestore_client=store,
        segment_update_fields=('is_user',),
        owner_recognition_diagnostics=live_data,
    )
    decoded = db.prepare_conversation_for_read(store.rows[path], 'u')
    assert decoded['transcript_segments'][0]['is_user'] is True
    assert decoded[contract.FIELD]['first_resolver']['reason'] == 'private_cloud_disabled'
    assert decoded[contract.FIELD]['live'][0]['attempted'] == 1


@pytest.mark.parametrize('fault', ['size', 'merge'])
def test_optional_metadata_failure_never_blocks_content_or_replaces_existing(monkeypatch, fault):
    current = {contract.FIELD: {'first_resolver': {'reason': 'resolved'}}, 'transcript_segments': 'existing'}
    patch = {contract.FIELD: {'live': [{'conversation': 'c'}]}, 'transcript_segments': 'new'}
    if fault == 'size':
        monkeypatch.setattr(db.document_size, 'estimate_firestore_document_bytes', lambda *a: 901 * 1024)
    else:
        monkeypatch.setattr(contract, 'merge', lambda *a: (_ for _ in ()).throw(ValueError('codec')))
    db._merge_owner_diagnostics(patch, current)
    assert patch == {'transcript_segments': 'new'} and current[contract.FIELD]['first_resolver']['reason'] == 'resolved'


def test_processing_merge_retains_concurrent_live_generation_and_immutable_first(monkeypatch):
    current = db.encode_conversation_for_write(
        'u',
        dict(
            transcript_segments=[],
            owner_recognition_diagnostics={
                'live': [dict(socket='s', conversation='c', sequence=4, attempted=4)],
                'first_resolver': {'reason': 'resolved'},
            },
        ),
        'standard',
    )
    patch = db.encode_conversation_for_write(
        'u',
        dict(
            transcript_segments=[],
            owner_recognition_diagnostics={
                'live': [dict(socket='s', conversation='c', sequence=1, attempted=1)],
                'first_resolver': {'reason': 'no_vectors'},
            },
        ),
        'standard',
    )
    db._reapply_current_manual_assignments('u', patch, current)
    assert patch[contract.FIELD]['live'][0]['attempted'] == 4
    assert patch[contract.FIELD]['first_resolver']['reason'] == 'resolved'


@pytest.mark.parametrize('case', ['missing', 'malformed', 'failed', 'ineligible'])
def test_profile_refusals_preserve_distinct_bounded_metadata(monkeypatch, caplog, case):
    monkeypatch.setattr(speakers, 'named_speaker_prompts_allowed', lambda uid: True)
    monkeypatch.setattr(speakers.user_db, 'get_people', lambda uid: [])

    def stored(uid):
        if case == 'failed':
            raise ValueError('SENSITIVE_PROVIDER_FAILURE')
        return [float('nan')] if case == 'malformed' else None

    monkeypatch.setattr(speakers.user_db, 'get_user_speaker_embedding', stored)
    matcher, host, _ = live(monkeypatch, [])
    host.persistence = _Persistence()
    host.has_speech_profile = False
    host.request.include_speech_profile = case != 'ineligible'
    matcher.person_embeddings.clear()
    caplog.set_level('INFO')
    asyncio.run(matcher._load_profiles())
    row = snapshot(matcher)
    expected = {
        'missing': 'profile_missing',
        'malformed': 'profile_invalid',
        'failed': 'profile_failed',
        'ineligible': 'profile_ineligible',
    }[case]
    assert row['reasons'][expected] == 1
    assert row['owner_profile_available'] == 0 and not matcher.person_embeddings
    assert 'SENSITIVE_PROVIDER_FAILURE' not in caplog.text


def test_actual_flush_with_no_identity_map_persists_only_diagnostic_field(monkeypatch):
    store = StrictFirestore()
    path = ('users', 'diagnostic-user', 'conversations', 'c')
    original = dict(id='c', transcript_segments=[], status='in_progress', content_revision=8)
    store.rows[path] = copy.deepcopy(original)
    matcher, host, _ = live(monkeypatch, [])
    host.speakers = matcher

    class Persistence:
        async def call(self, fn, *args, **kwargs):
            assert fn is db.update_owner_recognition_diagnostics
            return fn(*args, **kwargs, firestore_client=store)

    host.persistence = Persistence()
    processor = transcripts.TranscriptProcessor.__new__(transcripts.TranscriptProcessor)
    processor.host = host
    matcher.diagnostics.observe('no_prints', 'socket:0')
    matcher.diagnostics.stop('drain', matcher.queue, matcher.tasks)
    asyncio.run(processor.flush_speaker_assignments('c'))
    assert {k: v for k, v in store.rows[path].items() if k != contract.FIELD} == original
    assert store.rows[path][contract.FIELD]['live'][0]['reasons']['no_prints'] == 1


def test_unknown_old_generation_does_not_attribute_refusal_to_current(monkeypatch):
    matcher, _, _ = live(monkeypatch, [])
    asyncio.run(matcher.match(1, dict(_segment('old', 0, 5), conversation_id='unknown', _matcher_generation=0)))
    assert snapshot(matcher).get('reasons') == {}


def test_contract_huge_numeric_input_remains_bounded():
    assert contract.summary({'elapsed_seconds': 10**1000})['elapsed_seconds'] == 1e9


def test_scores_off_observation_does_not_change_accepted_identity(monkeypatch):
    monkeypatch.setenv('SPEAKER_MATCH_SCORES_ENABLED', 'false')
    matcher, _, _ = live(monkeypatch, [np.array([[1.0, 0.0]], dtype=np.float32)])
    matcher.person_embeddings.pop('p1')
    asyncio.run(matcher.match(1, _segment('s', 0, 65)))
    assert matcher.speaker_to_person[1][0] == 'user' and not matcher.match_scores
    assert snapshot(matcher)['reasons']['scores_disabled'] >= 1


def test_score_size_guard_deletion_is_not_reported_as_stored_scores():
    current = {contract.FIELD: {'first_resolver': {'reason': 'resolved'}}, 'speaker_match_scores': b'encoded'}
    patch = {
        contract.FIELD: {'live': [dict(conversation='c', scores_generated=1)]},
        'speaker_match_scores': db.firestore.DELETE_FIELD,
    }
    db._merge_owner_diagnostics(patch, current)
    assert patch[contract.FIELD]['live'][0]['scores'] == 'absent'


@pytest.mark.parametrize('fault', ['flag', 'codec'])
def test_optional_score_fault_does_not_interrupt_identity_publication(monkeypatch, fault):
    monkeypatch.setenv('SPEAKER_MATCH_SCORES_ENABLED', 'true')

    def fail(*args, **kwargs):
        raise ValueError('SENSITIVE_OPTIONAL_SCORE_FAILURE')

    monkeypatch.setattr(speakers.match_scores, 'enabled' if fault == 'flag' else 'summarize', fail)
    matcher, _, _ = live(monkeypatch, [np.array([[1.0, 0.0]], dtype=np.float32)])
    matcher.person_embeddings.pop('p1')
    asyncio.run(matcher.match(1, _segment('s', 0, 65)))
    assert matcher.speaker_to_person[1][0] == 'user'
    assert matcher.voice_identity_status[1].value == 'user'
    assert snapshot(matcher)['reasons']['scores_failed'] >= 1


@pytest.mark.parametrize('fail', [False, True])
def test_standalone_boundary_is_claimed_once_before_await_even_on_failure(monkeypatch, fail):
    matcher, host, _ = live(monkeypatch, [])
    host.speakers = matcher
    calls = []
    processor = transcripts.TranscriptProcessor.__new__(transcripts.TranscriptProcessor)
    processor.host = host

    async def persist(fn, *args, **kwargs):
        calls.append(copy.deepcopy(args[-1]))
        # Re-enter while the first persistence operation is still outstanding.
        await processor.flush_speaker_assignments('c')
        if fail:
            raise ConnectionError('synthetic')
        return True

    host.persistence = SimpleNamespace(call=persist)

    async def run():
        await processor.flush_speaker_assignments('c')
        assert not calls, 'active segment-loop flushes must not add diagnostic writes'
        matcher.diagnostics.checkpoint('c', matcher.queue, matcher.tasks)
        await processor.flush_speaker_assignments('c')
        # New sequence/pending counts, stop, and repeated boundaries do not retry.
        matcher.diagnostics.observe('no_pcm')
        matcher.diagnostics.stop('drain', matcher.queue, matcher.tasks)
        for _ in range(20):
            matcher.diagnostics.checkpoint('c', matcher.queue, matcher.tasks)
            await processor.flush_speaker_assignments('c')
        assert len(calls) == 1
        assert calls[0]['live'][0]['stop'] == 'finalized'
        # A successor owns its own single attempt.
        matcher.diagnostics.begin('c', matcher._generation + 1)
        matcher.diagnostics.stop('rollover', matcher.queue, matcher.tasks)
        await processor.flush_speaker_assignments('c')
        assert len(calls) == 2
        assert calls[1]['live'][0]['generation'] == matcher._generation + 1

    asyncio.run(run())
