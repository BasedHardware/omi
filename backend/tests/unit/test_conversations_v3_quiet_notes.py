"""Quiet notes: listen's quiet seal starts live-window notes before the five-minute close."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from config import conversations_v3 as config
from database import conversations_v3 as store, conversations_v3_leases as leases
from routers import conversations_v3_tasks as tasks
from utils.conversations.v3 import policy, quiet, service, summary
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

AT = datetime(2026, 11, 19, tzinfo=timezone.utc)
WORDS = [{'text': 'word ' * 400, 'start': 0, 'end': 60}]


def recording(**extra):
    return {
        'id': 'r',
        'status': 'completed',
        'started_at': AT,
        'finished_at': AT + timedelta(minutes=3),
        'transcript_segments': WORDS,
        **extra,
    }


def window(**extra):
    return {
        'id': 'c',
        'v3_derived': True,
        'status': 'in_progress',
        'finished_at': AT + timedelta(minutes=1),
        'v3_recording_ids': ['r'],
        **extra,
    }


def test_quiet_seal_is_proof_but_rotation_and_open_capture_are_not():
    assert quiet.proven(window(), {'r': recording()})
    assert not quiet.proven(window(), {'r': recording(**{policy.ROTATION_CAP_FIELD: 300})})
    assert not quiet.proven(window(), {'r': recording(status='in_progress')})
    assert not quiet.proven(window(), {'r': recording(status='processing')})
    assert not quiet.proven(window(), {'r': recording(_v3_page_continues=True)})
    assert not quiet.proven(window(), {'r': recording(record_audio_partial={'generation': 1})})


def test_closed_hidden_or_covered_windows_owe_no_quiet_notes():
    recordings = {'r': recording()}
    assert not quiet.proven(window(status='processing'), recordings)
    assert not quiet.proven(window(home_hidden=True), recordings)
    assert not quiet.proven(window(summary_covers_through=AT + timedelta(minutes=1)), recordings)
    assert quiet.proven(window(summary_covers_through=AT), recordings)


def test_latest_speech_decides_the_proof():
    later = recording(id='r2', started_at=AT + timedelta(minutes=4), **{policy.ROTATION_CAP_FIELD: 300})
    row = window(v3_recording_ids=['r', 'r2'])
    assert not quiet.proven(row, {'r': recording(), 'r2': later})


@pytest.mark.parametrize(
    'mode, member, expected',
    [('', True, False), ('off', True, False), ('cohort', False, False), ('cohort', True, True), ('on', False, True)],
)
def test_flag_defaults_off_with_cohort_canary(monkeypatch, mode, member, expected):
    if mode:
        monkeypatch.setenv('CONVERSATIONS_V3_QUIET_NOTES', mode)
    else:
        monkeypatch.delenv('CONVERSATIONS_V3_QUIET_NOTES', raising=False)
    monkeypatch.setattr(config, 'in_rollout_cohort', lambda uid, name: member and name == 'v3-quiet-notes')
    assert config.quiet_notes_enabled('u') is expected


def test_paid_attempts_are_capped_per_window_and_survive_reacquire(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(leases, 'get_firestore_client', lambda: client)

    def transactional(body):
        def run(tx, *args, **kwargs):
            with client.lock:
                return body(tx, *args, **kwargs)

        return run

    monkeypatch.setattr(quiet.firestore, 'transactional', transactional)
    token = leases.acquire('u', 'summary-c', firestore_client=client)
    assert not quiet._reserve('u', 'c', 'stale', firestore_client=client)
    assert quiet._reserve('u', 'c', token, firestore_client=client)
    leases.release('u', 'summary-c', token, firestore_client=client)
    token = leases.acquire('u', 'summary-c', firestore_client=client)
    assert quiet._reserve('u', 'c', token, firestore_client=client)
    assert not quiet._reserve('u', 'c', token, firestore_client=client)


@pytest.fixture
def seams(monkeypatch):
    calls = []
    live = window(transcript_segments=WORDS, kind='conversation')

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def reconcile(uid, **kwargs):
        calls.append(('reconcile', kwargs))
        return 'committed'

    async def prepare(uid, row):
        calls.append(('prepare', row['id']))
        return 'token'

    async def stream(uid, row, *, token):
        calls.append(('stream', token))
        yield 'data: ## Notes\n\n'
        yield summary.done(row)

    monkeypatch.setenv('CONVERSATIONS_V3_QUIET_NOTES', 'on')
    monkeypatch.setattr(quiet, 'run_blocking', blocking)
    monkeypatch.setattr(quiet, '_load', lambda uid, cid: dict(live))
    monkeypatch.setattr(quiet, '_reserve', lambda uid, cid, token: True)
    monkeypatch.setattr(leases, 'release', lambda *a: calls.append(('release',)))
    monkeypatch.setattr(service, 'reconcile', reconcile)
    monkeypatch.setattr(summary, 'prepare', prepare)
    monkeypatch.setattr(summary, 'stream', stream)
    import utils.generated_compute as compute

    monkeypatch.setattr(compute, 'require_generated_compute', lambda *a, **kw: None)
    return calls, live


@pytest.mark.asyncio
async def test_quiet_task_outlines_like_open_then_writes_through_the_on_open_writer(seams):
    calls, _ = seams
    assert await quiet.run('u', 'c') == 'stored'
    assert calls == [
        ('reconcile', {'on_open': True, 'conversation_id': 'c'}),
        ('prepare', 'c'),
        ('stream', 'token'),
    ]


@pytest.mark.asyncio
async def test_disabled_owner_spends_nothing(seams, monkeypatch):
    calls, _ = seams
    monkeypatch.setenv('CONVERSATIONS_V3_QUIET_NOTES', 'off')
    assert await quiet.run('u', 'c') == 'disabled'
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'patch', [{'status': 'processing'}, {'home_hidden': True}, {'kind': 'media'}, {'transcript_segments': []}]
)
async def test_closed_hidden_media_or_short_windows_make_no_notes_call(seams, monkeypatch, patch):
    calls, live = seams
    live.update(patch)
    assert await quiet.run('u', 'c') == 'skipped'
    assert ('prepare', 'c') not in calls


@pytest.mark.asyncio
async def test_spent_window_releases_the_lease_without_a_model_call(seams, monkeypatch):
    calls, _ = seams
    monkeypatch.setattr(quiet, '_reserve', lambda uid, cid, token: False)
    assert await quiet.run('u', 'c') == 'capped'
    assert calls[-1] == ('release',) and not any(c[0] == 'stream' for c in calls)


@pytest.mark.asyncio
async def test_busy_builder_or_writer_leaves_notes_to_the_close(seams, monkeypatch):
    calls, _ = seams

    async def busy(uid, **kwargs):
        return 'busy'

    monkeypatch.setattr(service, 'reconcile', busy)
    assert await quiet.run('u', 'c') == 'busy'

    async def held(uid, row):
        raise HTTPException(409, 'summary_in_progress')

    monkeypatch.setattr(service, 'reconcile', lambda uid, **kw: _done('committed'))
    monkeypatch.setattr(summary, 'prepare', held)
    assert await quiet.run('u', 'c') == 'busy'
    assert not any(c[0] == 'stream' for c in calls)


async def _done(value):
    return value


@pytest.mark.asyncio
async def test_task_route_dispatches_quiet_notes_and_keeps_plain_reconcile(monkeypatch):
    seen = []

    async def run(uid, cid):
        seen.append(('quiet', uid, cid))
        return 'stored'

    async def reconcile(uid):
        seen.append(('reconcile', uid))
        return 'committed'

    monkeypatch.setattr(quiet, 'run', run)
    monkeypatch.setattr(service, 'reconcile', reconcile)
    assert await tasks.reconcile(tasks.ReconcileRequest(uid='u', quiet_notes='c'), 0) == {'outcome': 'stored'}
    assert await tasks.reconcile(tasks.ReconcileRequest(uid='u'), 0) == {'outcome': 'committed'}
    assert seen == [('quiet', 'u', 'c'), ('reconcile', 'u')]


def test_task_name_is_one_per_window_end(monkeypatch):
    names = []
    monkeypatch.setattr(quiet, 'task_base', lambda: 'https://sync')
    monkeypatch.setattr(
        quiet, 'enqueue_named_task', lambda queue, url, name, payload, **kw: names.append((name, payload))
    )
    quiet.enqueue('u', window())
    quiet.enqueue('u', window())
    quiet.enqueue('u', window(finished_at=AT + timedelta(minutes=2)))
    assert names[0] == names[1] and names[0][0] != names[2][0]
    assert names[0][1] == {'uid': 'u', 'quiet_notes': 'c'} and names[0][0].startswith('conversations-v3-quiet-')


from tests.unit.test_conversations_v3_transactions import R, strict  # noqa: E402,F401
from tests.unit.test_conversations_v3_live_capture import live, loaded  # noqa: E402


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'mode, seal, expected',
    [('on', {}, 1), ('off', {}, 0), ('on', {policy.ROTATION_CAP_FIELD: 300}, 0), ('on', {'status': 'processing'}, 0)],
)
async def test_reconcile_queues_quiet_notes_only_for_an_enabled_quiet_seal(strict, monkeypatch, mode, seal, expected):
    import json
    from copy import deepcopy

    start = datetime.now(timezone.utc) - timedelta(minutes=2)
    strict.rows[R] = live(start, _test_revision=1, **{'status': 'completed', **seal})
    monkeypatch.setenv('CONVERSATIONS_V3_QUIET_NOTES', mode)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))
    original_load = store.load

    async def blocking(pool, fn, *args, **kwargs):
        if fn is original_load:
            return {'r': loaded(strict.rows[R], 1)}, {}, []
        return fn(*args, **kwargs)

    async def no_processing(uid):
        return None

    queued = []
    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', no_processing)
    monkeypatch.setattr(service, 'has_pending', lambda uid: False)
    monkeypatch.setattr(service, 'enqueue', lambda uid, at=None, **kw: None)
    monkeypatch.setattr(quiet, 'enqueue', lambda uid, row: queued.append(deepcopy(row)))
    monkeypatch.setattr(service.models, 'outline', lambda *a: pytest.fail('a live pass spends no outline call'))
    assert await service.reconcile('synthetic') == 'committed'
    assert len(queued) == expected
    if queued:
        assert queued[0]['status'] == 'in_progress' and json.dumps(queued[0]['v3_recording_ids']) == '["r"]'
