"""Quiet edges, exact input identity and bounded summary-only orchestration."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database import conversations_v3_quiet as attempts
from models.conversation import Conversation
from utils.conversations.v3 import quiet, summary_input, summary, triggers, service, renewal
from utils.conversations import process_conversation as process
from tests.unit.test_conversations_v3_stream import real_notes_seam

AT = datetime.now(timezone.utc) - timedelta(minutes=1)


def row(**extra):
    return {
        'id': 'c',
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=10),
        'status': 'in_progress',
        'tile_state': 'live',
        'v3_derived': True,
        'kind': 'conversation',
        'transcript_segments': [{'text': 'planning with Alice ' * 110, 'start': 0, 'end': 10, 'is_user': True}],
        'structured': {},
        **extra,
    }


def test_identity_survives_model_round_trip_and_transport_seal():
    original = row()
    model = Conversation(**original)
    assert summary_input.fingerprint(original) == summary_input.fingerprint(model)
    assert summary_input.fingerprint(original) == summary_input.fingerprint(
        {**original, 'status': 'completed', 'audio_files': [{'id': 'seal'}]}
    )


@pytest.mark.parametrize(
    'change',
    [
        {'finished_at': AT + timedelta(seconds=11)},
        {'started_at': AT - timedelta(seconds=1)},
        {'manual_end': True},
        {'kind': 'media'},
        {'language': 'fr'},
        {'transcript_segments': [{'text': 'same time corrected words', 'start': 0, 'end': 10, 'is_user': True}]},
        {
            'transcript_segments': [
                {'text': 'planning with Alice ' * 110, 'start': 0, 'end': 10, 'person_id': 'alice', 'is_user': False}
            ]
        },
    ],
)
def test_exact_coverage_rejects_changed_window_and_same_time_corrections(change):
    original = row()
    original.update(
        summary_covers_through=original['finished_at'], summary_input_hash=summary_input.fingerprint(original)
    )
    assert summary.fresh(original)
    assert not summary.fresh({**original, **change})
    assert not summary.fresh({**original, 'summary_covers_through': original['finished_at'] + timedelta(seconds=1)})


def test_old_timestamp_only_coverage_does_not_authorize_v3_reuse():
    original = row()
    assert not summary.fresh({**original, 'summary_covers_through': original['finished_at']})
    assert not summary.fresh({'finished_at': AT, 'summary_covers_through': AT + timedelta(seconds=1)})


def test_source_obligation_arms_once_per_content_and_not_per_transport_seal(monkeypatch):
    original = row(recording=True, v3_derived=False)
    snap = SimpleNamespace(to_dict=lambda: original)
    monkeypatch.setattr(attempts.store, 'decode_row', lambda *a: original)
    patch = attempts.source_patch('u', snap, now=AT)
    assert patch['v3_quiet_due'] == original['finished_at'] + timedelta(seconds=30)
    original.update(patch, status='completed', audio_files=[{'id': 'transport-seal'}])
    assert attempts.source_patch('u', snap, now=AT + timedelta(seconds=20)) == {}
    original['transcript_segments'][0]['text'] += ' corrected'
    assert attempts.source_patch('u', snap, now=AT + timedelta(seconds=20))['v3_quiet_pending']


def test_quiet_names_are_separate_from_manual_end_and_distinct_within_a_minute(monkeypatch):
    sent = []
    monkeypatch.setenv('CONVERSATIONS_V3_TASKS_URL', 'https://test.invalid')
    monkeypatch.setattr(triggers, 'enqueue_named_task', lambda *a, **kw: sent.append((a, kw)))
    triggers.enqueue('u', at=AT)
    triggers.enqueue('u', at=AT, manual_end_id='r')
    triggers.enqueue('u', at=AT, quiet_recording_id='r', quiet_generation='a' * 64)
    triggers.enqueue('u', at=AT + timedelta(seconds=1), quiet_recording_id='r', quiet_generation='b' * 64)
    triggers.enqueue('u', at=AT, quiet_recording_id='r', quiet_generation='a' * 64)
    assert len({call[0][2] for call in sent}) == 4
    assert sent[2] == sent[4]
    assert sent[2][0][3] == {'uid': 'u', 'quiet_recording_id': 'r', 'quiet_generation': 'a' * 64}


@pytest.mark.asyncio
async def test_old_quiet_delivery_does_no_reconcile_or_paid_work(monkeypatch):
    monkeypatch.setattr(attempts, 'obligation', lambda *a: None)
    monkeypatch.setattr(attempts, 'settle', lambda *a: None)
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=AssertionError('stale wake reconciled')))
    assert await quiet.run('u', 'r', 'old') == 'superseded'


def test_provisional_notes_recompute_at_real_close(real_notes_seam, monkeypatch):
    monkeypatch.setattr(process, 'content_minimum', lambda *a, **kw: None)
    monkeypatch.setattr(process, 'quiet_minimum', lambda *a, **kw: None)
    original = row()
    original.update(
        summary_covers_through=original['finished_at'],
        summary_input_hash=summary_input.fingerprint(original),
        summary_is_snapshot=True,
    )
    model = Conversation(**original)
    with summary.models.notes_mode('u'):
        structured, discarded = process._get_structured('u', 'en', model)
    assert len(real_notes_seam) == 1 and not discarded
    assert structured.sections[0].body_markdown


@pytest.mark.asyncio
async def test_cancelled_quiet_worker_keeps_lease_until_blocking_call_exits(monkeypatch):
    import threading

    entered, resume = threading.Event(), threading.Event()
    held, writes = [], []
    original = row(_v3_revision=1)

    async def blocking(pool, fn, *a, **kw):
        if fn is summary.write:
            return await asyncio.to_thread(fn, *a, **kw)
        return fn(*a, **kw)

    def write(*a):
        entered.set()
        assert resume.wait(3)
        return {'title': 'Snapshot'}

    monkeypatch.setattr(quiet, 'run_blocking', blocking)
    monkeypatch.setattr(renewal, 'run_blocking', blocking)
    monkeypatch.setattr(quiet.leases, 'acquire', lambda *a: held.append('token') or 'token')
    monkeypatch.setattr(quiet.leases, 'release', lambda *a: held.clear())
    monkeypatch.setattr(quiet, 'require_generated_compute', lambda *a, **kw: None)
    monkeypatch.setattr(
        attempts, 'reserve', lambda *a, **kw: {'row': original, 'revision': 1, 'sources': {}, 'input_hash': 'h'}
    )
    monkeypatch.setattr(summary, 'write', write)
    monkeypatch.setattr(summary.writers, 'store_summary', lambda *a, **kw: writes.append(a))
    task = asyncio.create_task(quiet.snapshot('u', original))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.001)
        assert entered.is_set()
        task.cancel()
        await asyncio.sleep(0)
        assert held == ['token'] and not task.done()
    finally:
        resume.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not held and not writes
