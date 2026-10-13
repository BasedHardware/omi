"""Pusher drain sees processing; the same bounded attempt repairs after completion."""

import asyncio
from collections import Counter
from concurrent.futures import Future
import threading

import pytest

from tests.unit.test_owner_repair_committed import (
    env,
    empty_manual_receipt,
    _commit_store,
    _counter,
    _capture_shifted_conversation,
    _install_audio,
    _span_flags,
    VOICES,
)
from utils import executors
from utils.conversations import speaker_identity_retry as retry, speaker_resolution as stage
from utils.observability.owner_identity_retry import OWNER_IDENTITY_RETRY


def funnel(stage_name, reason):
    return OWNER_IDENTITY_RETRY.labels(**{'pass': 'late', 'stage': stage_name, 'reason': reason})._value.get()


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
async def test_scan_processing_then_completion_persists_owner(env, monkeypatch, level):
    _span_flags(monkeypatch)
    _install_audio(monkeypatch, [0, 0], offset=180.0)
    conversation = _capture_shifted_conversation([0, 0])
    for segment in conversation.transcript_segments:
        segment.speaker_id_scope = 'conversation:c1'
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: VOICES[0].tolist())
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda uid: False)
    store, path, read = _commit_store(monkeypatch, conversation, level)
    store.rows[path]['status'] = 'processing'
    first_read = asyncio.Event()
    loop = asyncio.get_running_loop()
    reads = []

    def read_snapshot(*args):
        raw = read(*args)
        reads.append(raw['status'])
        if len(reads) == 1:
            loop.call_soon_threadsafe(first_read.set)
        return raw

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read_snapshot)
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (0,), raising=False)
    before = _counter('owner_added')
    stages = {
        pair: funnel(*pair)
        for pair in [
            ('entry', 'candidate'),
            ('eligible', 'candidate'),
            ('cas_committed', 'done'),
            ('skipped', 'not_completed'),
        ]
    }
    assert retry.schedule_completed_identity_retries('u1', ['c1'])
    await asyncio.wait_for(first_read.wait(), 2)
    # A competing upload-drain trigger coalesces with the deferred attempt.
    assert retry.schedule_completed_identity_retries('u1', ['c1'])
    assert not any(s['is_user'] for s in read()['transcript_segments'])
    store.rows[path]['status'] = 'completed'
    await asyncio.gather(*list(executors._background_tasks))
    # Real resolver -> encrypted/compressed CAS -> readable client transcript.
    assert all(s['is_user'] for s in read()['transcript_segments'])
    assert reads == ['processing', 'completed']
    assert _counter('owner_added') == before + 1
    assert {pair: funnel(*pair) - n for pair, n in stages.items()} == {
        ('entry', 'candidate'): 1,
        ('eligible', 'candidate'): 1,
        ('cas_committed', 'done'): 1,
        ('skipped', 'not_completed'): 0,
    }


async def test_completion_wait_is_bounded_and_one_terminal_skip(monkeypatch):
    reads = []
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (0,) * 5)

    def read(uid, cid):
        reads.append(cid)
        return {'status': 'processing'}

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', lambda *a, **kw: pytest.fail('not completed'))
    before = funnel('skipped', 'not_completed')
    assert retry.schedule_completed_identity_retries('u', ['pending'])
    await asyncio.gather(*list(executors._background_tasks))
    assert reads == ['pending'] * 6
    assert funnel('skipped', 'not_completed') == before + 1
    assert not retry._active


async def test_eight_passes_and_128_candidates_include_all_rechecks(monkeypatch):
    reads = Counter()
    repairs = []
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (0,) * 5)

    def read(uid, cid):
        reads[cid] += 1
        return {
            'status': 'completed' if cid < 'c007' or reads[cid] > 1 else 'processing',
            'private_cloud_sync_enabled': True,
            'updated_at': 'revision',
        }

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', lambda uid, cid, **kw: repairs.append(cid))
    before = {
        pair: funnel(*pair) for pair in [('entry', 'candidate'), ('skipped', 'scan_limit'), ('skipped', 'pass_limit')]
    }
    assert retry.schedule_completed_identity_retries('u', [f'c{i:03}' for i in range(129)])
    await asyncio.gather(*list(executors._background_tasks))
    assert repairs == [f'c{i:03}' for i in range(8)]
    assert len(reads) == 128 and sum(reads.values()) == 129
    assert {pair: funnel(*pair) - n for pair, n in before.items()} == {
        ('entry', 'candidate'): 129,
        ('skipped', 'scan_limit'): 1,
        ('skipped', 'pass_limit'): 120,
    }


@pytest.mark.parametrize(
    'changed,reason',
    [
        ({'deleted': True}, 'deleted'),
        ({'discarded': True}, 'discarded'),
        ({'is_locked': True}, 'locked'),
        ({'source': 'desktop'}, 'channel_source'),
        ({'private_cloud_sync_enabled': False}, 'private_cloud_disabled'),
        ({'updated_at': None}, 'missing_revision'),
        ({'status': 'failed'}, 'not_completed'),
    ],
)
async def test_rechecks_do_not_bypass_lifecycle_or_policy(monkeypatch, changed, reason):
    calls = []
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (0,) * 5)

    def read(uid, cid):
        calls.append(cid)
        return (
            {'status': 'processing'}
            if len(calls) == 1
            else {
                'status': 'completed',
                'private_cloud_sync_enabled': True,
                'updated_at': 'revision',
                **changed,
            }
        )

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', lambda *a, **kw: pytest.fail('gate bypassed'))
    before = funnel('skipped', reason)
    assert retry.schedule_completed_identity_retries('u', ['pending'])
    await asyncio.gather(*list(executors._background_tasks))
    assert len(calls) == 2
    assert funnel('skipped', reason) == before + 1


async def test_cancellation_before_coordinator_starts_keeps_running_worker_slot(monkeypatch):
    future = Future()
    monkeypatch.setattr(retry, '_slots', threading.BoundedSemaphore(2))
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a: future)
    assert retry.schedule_completed_identity_retries('u', ['first'])
    task = next(iter(executors._background_tasks))
    task.cancel()  # coroutine has not entered its first await/finally
    await asyncio.gather(task, return_exceptions=True)
    assert ('u', 'first') in retry._active
    assert retry._slots.acquire(blocking=False)
    assert not retry._slots.acquire(blocking=False)
    future.set_result(retry.RetryRound(('first',), 0))
    assert ('u', 'first') not in retry._active
    assert retry._slots.acquire(blocking=False)
