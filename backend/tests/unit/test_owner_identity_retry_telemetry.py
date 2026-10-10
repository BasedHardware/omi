"""Closed funnel and resolver diagnostics, preserving the existing outcomes."""

import asyncio
import importlib
import os
import subprocess
import sys
import types
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import Future

import pytest

from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    empty_manual_receipt,
    _conversation,
    _span_flags,
    _install_audio,
    _capture_shifted_conversation,
)
from tests.unit.test_owner_repair_committed import _commit_store
from utils.conversations import speaker_resolution as stage, speaker_identity_retry as retry
from utils.conversations import process_conversation as processing
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_owner_recognition_telemetry import (
    _wire_sync_store,
    _stub_sync_enrichment,
    _sync_segment,
    _sync_incoming,
)
from utils.observability import owner_identity_retry as telemetry, owner_recognition
from utils import executors


def count(pass_name, stage, reason):
    return telemetry.OWNER_IDENTITY_RETRY.labels(**{'pass': pass_name, 'stage': stage, 'reason': reason})._value.get()


def snapshot(pass_name):
    return {(s, r): count(pass_name, s, r) for s, r in telemetry.PAIRS}


def delta(pass_name, before):
    return {pair: count(pass_name, *pair) - n for pair, n in before.items() if count(pass_name, *pair) != n}


def test_registration_reuses_collector_and_only_materializes_closed_pairs():
    counter = telemetry.OWNER_IDENTITY_RETRY
    telemetry.record_retry('late', 'resolver_exit', 'resolved')
    importlib.reload(telemetry)
    assert telemetry.OWNER_IDENTITY_RETRY is counter
    assert len(telemetry.PAIRS) == 60
    assert len(telemetry.PAIRS - {p for p in telemetry.PAIRS if p[0] in ('resolver_exit', 'segment_abstained')}) == 28
    assert set(counter._metrics) <= {(p, s, r) for p in ('first', 'late') for s, r in telemetry.PAIRS}
    assert len(counter._metrics) < 120
    before = snapshot('late')
    telemetry.record_retry('late', 'dynamic-conversation-id', 'dynamic-uid')
    assert delta('late', before) == {('skipped', 'processing_error'): 1}
    assert set(counter._metrics) <= {(p, s, r) for p in ('first', 'late') for s, r in telemetry.PAIRS}


def test_counter_failure_is_nonfatal(monkeypatch):
    def fail(**kw):
        raise RuntimeError('collector failure')

    monkeypatch.setattr(telemetry.OWNER_IDENTITY_RETRY, 'labels', fail)
    telemetry.record_retry('first', 'resolver_exit', 'resolved')


@pytest.mark.parametrize('pass_name', ['first', 'late'])
@pytest.mark.parametrize(
    'case,reason',
    [
        ('disabled', 'disabled'),
        ('private_cloud', 'no_audio'),
        ('all_short', 'all_short'),
        ('missing_position', 'no_proven_window'),
        ('spanless', 'manifest_unvalidated'),
        ('zero', 'resolved'),
        ('invalid', 'partial'),
        ('overlap_and_zero', 'global_manifest_ambiguity'),
        ('hole', 'capture_coverage_hole'),
        ('resolved', 'resolved'),
        ('embedding_budget', 'embedding_budget'),
        ('embedding_failed', 'embedding_failed'),
    ],
)
def test_real_resolver_emits_one_primary_exit(env, monkeypatch, pass_name, case, reason):
    _span_flags(monkeypatch)
    _install_audio(monkeypatch, [0, 0], offset=180.0)
    conversation = _capture_shifted_conversation([0, 0])
    kwargs = {}
    if case == 'disabled':
        monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    elif case == 'private_cloud':
        conversation.private_cloud_sync_enabled = False
    elif case == 'all_short':
        for s in conversation.transcript_segments:
            s.end = s.start + 0.1
    elif case == 'missing_position':
        for s in conversation.transcript_segments:
            s.audio_capture_start = s.audio_capture_end = None
    elif case == 'spanless':
        for f in conversation.audio_files:
            f.chunk_spans = []
    elif case in ('zero', 'overlap_and_zero'):
        conversation.transcript_segments[1].end = conversation.transcript_segments[1].start
        if case == 'overlap_and_zero':
            conversation.audio_files.append(conversation.audio_files[0].model_copy(deep=True))
    elif case == 'invalid':
        conversation.transcript_segments[1].start = -1
    elif case == 'hole':
        # Valid placement for the first segment; a complete provider window
        # beyond proven coverage triggers the existing global veto.
        conversation.transcript_segments[1].audio_capture_start += 1000
        conversation.transcript_segments[1].audio_capture_end += 1000
    elif case == 'embedding_budget':
        kwargs['max_embedding_attempts'] = 0
    elif case == 'embedding_failed':
        env[1].fail = True
    before = snapshot(pass_name)
    with telemetry.identity_pass(pass_name):
        assert stage.resolve_speakers_for_processing('u1', conversation, **kwargs)
    expected = {('resolver_exit', reason): 1}
    if case in ('zero', 'overlap_and_zero', 'invalid'):
        skipped_reason = 'invalid_text_window' if case == 'invalid' else 'zero_text_window'
        expected[('segment_abstained', skipped_reason)] = 1
    if pass_name == 'first':
        expected.update({('entry', 'candidate'): 1, ('eligible', 'candidate'): 1})
    assert delta(pass_name, before) == expected
    if case in ('zero', 'invalid'):
        assert conversation.speaker_resolution.status == ('unavailable' if case == 'invalid' else 'resolved')
        assert not conversation.transcript_segments[1].is_user


@pytest.mark.parametrize('pass_name', ['first', 'late'])
def test_empty_does_not_invent_acoustic_exit(env, pass_name):
    before = snapshot(pass_name)
    with telemetry.identity_pass(pass_name):
        assert not stage.resolve_speakers_for_processing('u1', _conversation([]))
    expected = {('entry', 'candidate'): 1, ('skipped', 'empty_transcript'): 1} if pass_name == 'first' else {}
    assert delta(pass_name, before) == expected


@pytest.mark.parametrize(
    'overrides,reason',
    [
        ({'status': 'in_progress', 'deleted': True}, 'not_completed'),
        ({'deleted': True, 'discarded': True}, 'deleted'),
        ({'discarded': True}, 'discarded'),
        ({'is_locked': True}, 'locked'),
        ({'source': 'desktop'}, 'channel_source'),
        ({'private_cloud_sync_enabled': False}, 'private_cloud_disabled'),
        ({'updated_at': None}, 'missing_revision'),
        (
            {'speaker_resolution': {'status': 'resolved'}, 'transcript_segments': [{'is_user': True}]},
            'already_resolved_owner',
        ),
    ],
)
def test_eligibility_uses_existing_precedence(overrides, reason):
    raw = {'status': 'completed', 'private_cloud_sync_enabled': True, 'updated_at': 'revision', **overrides}
    assert stage.completed_identity_retry_skip_reason(raw) == reason
    assert not stage.completed_identity_retry_eligible(raw)


def test_batch_pass_cap_and_skips_preserve_reads_and_attempts(monkeypatch):
    reads, repairs = [], []

    def read(uid, cid):
        reads.append(cid)
        return {
            'id': cid,
            'status': 'in_progress' if cid == 'c00' else 'completed',
            'private_cloud_sync_enabled': True,
            'updated_at': 'revision',
        }

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', lambda uid, cid, **kw: repairs.append(cid))
    before = snapshot('late')
    result = retry._retry_batch('u', tuple(f'c{i:02}' for i in range(11)))
    assert reads == [f'c{i:02}' for i in range(9)]
    assert repairs == [f'c{i:02}' for i in range(1, 9)]
    assert result.pending == ('c00',) and result.attempted == 8
    # A processing row is now an unfinished attempt until the coordinator's
    # bounded completion rechecks finish, rather than an immediate terminal.
    assert delta('late', before) == {('skipped', 'pass_limit'): 2}


def test_slot_denial_counts_deduplicated_candidates_and_keeps_return(monkeypatch):
    monkeypatch.setattr(retry, '_slots', SimpleNamespace(acquire=lambda **kw: False))
    before = snapshot('late')
    assert not retry.schedule_completed_identity_retries('u', ['c1', 'c1', 'c2'])
    assert delta('late', before) == {('entry', 'candidate'): 2, ('skipped', 'slot_limit'): 2}


async def test_scan_cap_preserves_submitted_candidates(monkeypatch):
    submitted, released = [], []
    future = Future()

    def submit(executor, fn, uid, candidates):
        submitted.extend(candidates)
        return future

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    monkeypatch.setattr(
        retry, '_slots', SimpleNamespace(acquire=lambda **kw: True, release=lambda: released.append(True))
    )
    before = snapshot('late')
    assert retry.schedule_completed_identity_retries('u', [f'c{i:03}' for i in range(130)])
    assert submitted == [f'c{i:03}' for i in range(128)]
    assert delta('late', before) == {('entry', 'candidate'): 130, ('skipped', 'scan_limit'): 2}
    assert not released
    future.set_result(retry.RetryRound((), 0))
    await asyncio.gather(*list(executors._background_tasks))
    assert released == [True]


def test_submission_failure_still_raises_and_releases_slot(monkeypatch):
    released = []

    def fail(*args):
        raise RuntimeError('submit failed')

    monkeypatch.setattr(retry, 'submit_with_context', fail)
    monkeypatch.setattr(
        retry, '_slots', SimpleNamespace(acquire=lambda **kw: True, release=lambda: released.append(True))
    )
    before = snapshot('late')
    with pytest.raises(RuntimeError, match='submit failed'):
        retry.schedule_completed_identity_retries('u', ['c1'])
    assert delta('late', before) == {('entry', 'candidate'): 1, ('skipped', 'submission_error'): 1}
    assert released == [True]


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_late_noop_commit_counts_terminal_but_neither_existing_outcome_counter(env, monkeypatch, level):
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    _, _, read = _commit_store(monkeypatch, _capture_shifted_conversation([0]), level)
    existing = {
        counter: tuple(child._value.get() for child in counter._metrics.values())
        for counter in (owner_recognition.OWNER_IDENTITY_REPAIR, owner_recognition.OWNER_RECOGNITION_CONVERSATIONS)
    }
    before = snapshot('late')
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    assert delta('late', before) == {
        ('entry', 'candidate'): 1,
        ('eligible', 'candidate'): 1,
        ('resolver_exit', 'disabled'): 1,
        ('cas_committed', 'done'): 1,
    }
    assert {
        counter: tuple(child._value.get() for child in counter._metrics.values()) for counter in existing
    } == existing


@pytest.mark.parametrize(
    'change,reason',
    [
        ({'deleted': True}, 'deleted'),
        ({'discarded': True}, 'discarded'),
        ({'is_locked': True}, 'locked'),
        ({'status': 'in_progress'}, 'not_completed'),
        ({}, 'revision_changed'),
    ],
)
def test_cas_refusal_is_terminal_and_never_a_repair(env, monkeypatch, change, reason):
    conv = _capture_shifted_conversation([0])
    store, path, read = _commit_store(monkeypatch, conv, 'enhanced')
    candidate = read()
    store.rows[path].update(change)
    if not change:
        candidate['updated_at'] -= timedelta(seconds=1)
    before = snapshot('late')
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    assert not stage.refresh_completed_speaker_identity('u1', 'c1', candidate=candidate)
    assert delta('late', before) == {
        ('eligible', 'candidate'): 1,
        ('resolver_exit', 'disabled'): 1,
        ('cas_refused', reason): 1,
    }


@pytest.fixture
def baseline_module(monkeypatch):
    # Pin to the task's origin/main base. Compare the exact pre-telemetry
    # implementation, not a mock mirroring the new code.
    base = 'a1cfd2683b38cff64522a890acb5ea8467ef0567'
    source = subprocess.run(
        ['git', 'show', f'{base}:backend/utils/conversations/speaker_resolution.py'],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    module = types.ModuleType('owner_retry_funnel_baseline')
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(source, 'baseline_speaker_resolution.py', 'exec'), module.__dict__)
    return module


@pytest.mark.parametrize('case', ['resolved', 'zero', 'spanless', 'partial', 'disabled', 'failed_embedding'])
def test_literal_baseline_and_instrumented_outputs_and_cache_bytes_identical(env, monkeypatch, baseline_module, case):
    _span_flags(monkeypatch)
    audio = _install_audio(monkeypatch, [0, 0], offset=180.0)
    original = _capture_shifted_conversation([0, 0])
    if case == 'zero':
        original.transcript_segments[1].end = original.transcript_segments[1].start
    elif case == 'spanless':
        original.audio_files[0].chunk_spans = []
    elif case == 'partial':
        original.transcript_segments[1].audio_capture_start = original.transcript_segments[1].audio_capture_end = None
    elif case == 'disabled':
        monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    elif case == 'failed_embedding':
        env[1].fail = True
    store, diarizer = env
    for name in (
        'speaker_embedding_configured',
        'named_speaker_prompts_allowed',
        'download_speaker_embedding_cache',
        'upload_speaker_embedding_cache',
        'extract_embedding_from_bytes',
        'AudioChunkReadSession',
        'iter_audio_chunk_pcm',
        '_verified_read_session',
    ):
        monkeypatch.setattr(baseline_module, name, getattr(stage, name))
    first = original.model_copy(deep=True)
    second = original.model_copy(deep=True)
    old_result = baseline_module.resolve_speakers_for_processing('u1', first)
    old_cache = deepcopy(store)
    store.clear()
    diarizer.calls = 0
    with telemetry.identity_pass('first'):
        new_result = stage.resolve_speakers_for_processing('u1', second)
    assert old_result == new_result
    if case == 'zero':
        # This task deliberately changes the pinned baseline's whole-row veto.
        # Keep an explicit before/after proof instead of asserting equivalence.
        assert first.speaker_resolution.status == 'unavailable'
        assert second.speaker_resolution.status == 'resolved'
        assert first.transcript_segments[1].model_dump() == second.transcript_segments[1].model_dump()
        assert old_cache == {}
        assert len(stage.decode_cache(store['c1'])) == 1
        return
    assert first.model_dump_json() == second.model_dump_json()
    assert old_cache == store  # Includes byte-identical encoded owner-evidence cache.


@pytest.mark.parametrize(
    'failure,reason',
    [
        ('budget', 'read_budget'),
        ('listing', 'listing_limit'),
        ('generation', 'inventory_metadata_invalid'),
        ('manifest', 'manifest_inventory_invalid'),
        ('count', 'inventory_count_mismatch'),
        ('pair', 'inventory_pair_mismatch'),
        ('missing', 'blob_missing'),
        ('read', 'blob_read_failed'),
        ('decode', 'blob_decode_failed'),
        ('odd_pcm', 'blob_decode_failed'),
        ('download_cap', 'read_budget'),
        ('duration', 'decoded_duration_mismatch'),
        ('overlap', 'decoded_overlap'),
        ('coverage', 'decoded_coverage_hole'),
        ('window', 'no_proven_window'),
    ],
)
def test_actual_inventory_proof_primary_reason_and_unchanged_io(env, monkeypatch, baseline_module, failure, reason):
    conv = _capture_shifted_conversation([0])
    origin = conv.audio_files[0].chunk_timestamps[0]
    chunks = [
        {
            'path': 'fixture',
            'generation': 1,
            'timestamp': origin,
            'span': {'start': origin, 'samples': 4 * stage.SAMPLE_RATE, 'sample_rate': stage.SAMPLE_RATE},
        }
    ]
    files = [f.model_dump() for f in conv.audio_files]
    placements = {'s0': stage.AudioPlacement((origin, origin + 3.8), 'capture_span')}
    pcm = b'\x00\x00' * (4 * stage.SAMPLE_RATE)
    fetch_reason = 'none'
    if failure == 'listing':
        chunks *= stage.MAX_ADVISORY_PLACEMENTS + 1
    elif failure == 'generation':
        chunks[0]['generation'] = 0
    elif failure == 'manifest':
        files[0]['chunk_timestamps'] = [float('nan')]
    elif failure == 'count':
        chunks = []
    elif failure == 'pair':
        chunks[0]['timestamp'] += 1
    elif failure in ('missing', 'read', 'decode'):
        pcm = None
        fetch_reason = {'missing': 'missing_blob', 'read': 'download_failed', 'decode': 'decode_failed'}[failure]
    elif failure == 'odd_pcm':
        pcm = b'x'
    elif failure == 'duration':
        pcm = b'\x00\x00' * stage.SAMPLE_RATE
    elif failure == 'overlap':
        chunks.append({**chunks[0], 'path': 'second'})
        files.append(deepcopy(files[0]))
    elif failure == 'coverage':
        placements['s0'] = stage.AudioPlacement((origin, origin + 5), 'capture_span')
    elif failure == 'window':
        placements['s0'] = stage.AudioPlacement(None, 'untrusted_clock')
    reads = []

    class Session:
        def __init__(self, *args):
            self.deadline = float('inf')
            self.chunks = chunks
            self.limit_hit = False
            self.reason = fetch_reason

        def in_budget(self):
            return failure != 'budget'

        def fetch(self, path):
            reads.append(path)
            if failure == 'download_cap':
                self.limit_hit = True
            return pcm

    monkeypatch.setattr(stage, 'AudioChunkReadSession', Session)
    monkeypatch.setattr(baseline_module, 'AudioChunkReadSession', Session)
    baseline = baseline_module._verified_read_session(
        'u1', conv, files, conv.transcript_segments, placements, float('inf')
    )
    baseline_reads = list(reads)
    reads.clear()
    with telemetry.identity_pass('late'):
        result = stage._verified_read_session('u1', conv, files, conv.transcript_segments, placements, float('inf'))
        assert telemetry.resolver_trace().reason == reason
    assert result is None and baseline is None
    assert reads == baseline_reads


@pytest.mark.parametrize(
    'extra,reason', [({'missing': True}, 'missing'), ({'account_deleting': True}, 'account_deleting')]
)
def test_remaining_cas_refusals(env, monkeypatch, extra, reason):
    conv = _capture_shifted_conversation([0])
    store, path, read = _commit_store(monkeypatch, conv, 'standard')
    candidate = read()
    if 'missing' in extra:
        del store.rows[path]
    else:
        store.rows[('account_deletions', 'u1')] = {'wipe_status': 'pending'}
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    before = snapshot('late')
    assert not stage.refresh_completed_speaker_identity('u1', 'c1', candidate=candidate)
    assert delta('late', before) == {
        ('eligible', 'candidate'): 1,
        ('resolver_exit', 'disabled'): 1,
        ('cas_refused', reason): 1,
    }


def test_cas_callback_is_outside_transaction_replays(env, monkeypatch):
    # Exercise the real writer's transaction callback twice with read-only
    # refusal snapshots, then return only the final transaction result. This
    # models SDK callback retries without claiming the strict fake models retries.
    conv = _capture_shifted_conversation([0])
    store, path, read = _commit_store(monkeypatch, conv, 'standard')
    payload = read()
    store.rows[path]['discarded'] = True
    events = []

    def replay_decorator(fn):
        def wrapped(transaction):
            assert fn(transaction) == (False, 'discarded', None)
            assert events == []
            return fn(transaction)

        return wrapped

    monkeypatch.setattr(stage.identity_updates_db.firestore, 'transactional', replay_decorator)
    assert not stage.identity_updates_db.persist_speaker_resolution_if_current(
        'u1', payload, expected_updated_at=payload['updated_at'], on_outcome=lambda *e: events.append(e)
    )
    assert events == [('cas_refused', 'discarded')]


def test_cas_observer_failure_cannot_change_commit(env, monkeypatch):
    conv = _capture_shifted_conversation([0])
    _, _, read = _commit_store(monkeypatch, conv, 'enhanced')
    payload = read()

    def fail(*args):
        raise RuntimeError('collector failed')

    assert stage.identity_updates_db.persist_speaker_resolution_if_current(
        'u1', payload, expected_updated_at=payload['updated_at'], on_outcome=fail
    )


def test_post_commit_failure_does_not_double_count_terminal(env, monkeypatch):
    conv = _capture_shifted_conversation([0])
    _commit_store(monkeypatch, conv, 'standard')
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')

    def fail(*args):
        raise RuntimeError('cache invalidation failed')

    monkeypatch.setattr(stage.conversations_db, 'invalidate_people_stats_cache', fail)
    before = snapshot('late')
    assert not stage.refresh_completed_speaker_identity('u1', 'c1')  # Original return behavior.
    assert delta('late', before) == {
        ('entry', 'candidate'): 1,
        ('eligible', 'candidate'): 1,
        ('resolver_exit', 'disabled'): 1,
        ('cas_committed', 'done'): 1,
    }


def test_contexts_do_not_leak_between_first_late_and_reprocess(env, monkeypatch):
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    before = snapshot('first'), snapshot('late')
    with telemetry.identity_pass('first'):
        with telemetry.identity_pass('late'):
            assert stage.resolve_speakers_for_processing('u1', _conversation([0]))
        assert stage.resolve_speakers_for_processing('u1', _conversation([0]))
    assert stage.resolve_speakers_for_processing('u1', _conversation([0]))
    assert delta('first', before[0]) == {
        ('entry', 'candidate'): 1,
        ('eligible', 'candidate'): 1,
        ('resolver_exit', 'disabled'): 1,
    }
    assert delta('late', before[1]) == {('resolver_exit', 'disabled'): 1}


def test_first_finalization_pipeline_emits_funnel_without_counting_reprocess(env, monkeypatch, baseline_module):
    store = StrictFirestore()
    lifecycle, pipeline = _wire_sync_store(monkeypatch, store)
    _stub_sync_enrichment(monkeypatch, store)
    # The real lifecycle, processing dispatcher, resolver and persistence path.
    # Only model/provider work is stubbed, as in the existing outcome tests.
    monkeypatch.setattr(
        processing,
        'resolve_speakers_for_processing',
        (
            baseline_module.resolve_speakers_for_processing
            if os.getenv('OMI_OWNER_RETRY_RED') == '1'
            else stage.resolve_speakers_for_processing
        ),
    )
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'true')
    segment = _sync_segment(
        text='We agreed to ship the recognition fix today.', is_user=True, end=8.0, scope='sync:keep'
    )
    assigned, created, _ = lifecycle.ingest_sync_conversation('u', _sync_incoming('keep', 1_700_000_000, segment))
    assert created
    before = snapshot('first')
    pipeline._reprocess_conversation_after_update('u', assigned['id'], 'en')
    assert delta('first', before) == {
        ('entry', 'candidate'): 1,
        ('eligible', 'candidate'): 1,
        ('resolver_exit', 'no_audio'): 1,
    }
    row = store.rows[('users', 'u', 'conversations', assigned['id'])]
    assert row['status'] == 'completed'
    before = snapshot('first')
    pipeline._reprocess_conversation_after_update('u', assigned['id'], 'en')
    assert delta('first', before) == {}
