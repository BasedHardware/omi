"""Deterministic reconcile conflicts: adoption, owner backoff, kept outlines and late-text coverage."""

from datetime import datetime, timedelta, timezone

import pytest

from database import conversations_v3 as store
from utils.conversations.v3 import Conflict, service
from tests.unit.test_conversations_v3_review import AT, MemoryQuery, builder, source  # noqa: F401


@pytest.mark.asyncio
async def test_planned_id_outside_the_closure_is_adopted_as_prior(builder, monkeypatch):
    committed, _ = builder
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    planned = []

    def adoptable(uid, ids):
        planned.extend(ids)
        return {
            ids[0]: {
                'id': ids[0],
                'v3_derived': True,
                'started_at': AT,
                'finished_at': AT + timedelta(seconds=10),
                'status': 'completed',
                'tile_state': 'done',
                'title_locked': True,
                'v3_recording_ids': ['r'],
                'transcript_segments': [{'text': 'speech for a synthetic plan', 'start': 0, 'end': 10}],
            }
        }

    monkeypatch.setattr(store, 'adoptable', adoptable)
    assert await service.reconcile('u') == 'committed'
    _uid, _token, _recordings, existing, rows, _cache = committed[0]
    assert len(planned) == 1 and planned[0] in existing
    assert [row['id'] for row in rows] == planned
    # Replanned with the stored row as prior: the user's lock survives instead of a blind overwrite.
    assert rows[0]['title_locked'] is True


@pytest.mark.asyncio
async def test_no_adoption_when_every_planned_row_is_loaded(builder, monkeypatch):
    committed, _ = builder
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    calls = []
    monkeypatch.setattr(store, 'adoptable', lambda uid, ids: calls.append(ids) or {})
    await service.reconcile('u')
    assert len(committed) == 1 and len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['target_exists', 'multiple_open_conversations', 'v3_derived_budget'])
async def test_deterministic_conflict_answers_the_task_and_backs_the_owner_off(builder, monkeypatch, reason):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))

    def conflict(*a, **kw):
        raise Conflict(reason)

    monkeypatch.setattr(service, '_commit', conflict)
    blocked = []
    monkeypatch.setattr(store, 'record_blocked', lambda uid, why: blocked.append(why))
    assert await service.reconcile('u') == 'blocked'
    assert blocked == [reason]


@pytest.mark.asyncio
async def test_race_conflicts_still_raise_for_a_task_retry(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))

    def conflict(*a, **kw):
        raise Conflict('source_changed')

    monkeypatch.setattr(service, '_commit', conflict)
    monkeypatch.setattr(store, 'record_blocked', lambda *a: pytest.fail('a race is not a blocked owner'))
    with pytest.raises(Conflict):
        await service.reconcile('u')


@pytest.mark.asyncio
async def test_backed_off_owner_skips_without_taking_the_lease(builder, monkeypatch):
    monkeypatch.setattr(store, 'backoff_until', lambda uid: datetime.now(timezone.utc) + timedelta(minutes=5))
    monkeypatch.setattr(service.leases, 'acquire', lambda *a: pytest.fail('backoff must not take the lease'))
    assert await service.reconcile('u') == 'backoff'


@pytest.mark.asyncio
async def test_open_conversation_bypasses_owner_backoff(builder, monkeypatch):
    monkeypatch.setattr(store, 'backoff_until', lambda uid: pytest.fail('on-open is the user waiting'))
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({}, {}, []))
    await service.reconcile('u', on_open=True, conversation_id='c')


@pytest.mark.asyncio
async def test_paid_outline_is_kept_when_the_commit_conflicts(builder, monkeypatch):
    _, messages = builder
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    saved = []
    monkeypatch.setattr(store, 'save_outline', lambda uid, token, fp, entries: saved.append((fp, entries)))

    def conflict(*a, **kw):
        raise Conflict('target_exists')

    monkeypatch.setattr(service, '_commit', conflict)
    monkeypatch.setattr(store, 'record_blocked', lambda *a: None)
    await service.reconcile('u')
    assert len(messages) == 1
    assert len(saved) == 1 and saved[0][1][0]['title'] == 'A plan'


def test_backoff_doubles_to_an_hour_and_success_clears_it(monkeypatch):
    rows = {}
    client = MemoryQuery(rows)

    class Ref:
        def __init__(self, path):
            self.path = path

        def get(self):
            from types import SimpleNamespace

            return SimpleNamespace(to_dict=lambda: rows.get(self.path), exists=self.path in rows)

        def set(self, data, merge=False):
            rows[self.path] = {**(rows.get(self.path) or {}), **data} if merge else data

    monkeypatch.setattr(store.leases, 'lease_ref', lambda client, uid, key: Ref(f'{uid}/{key}'))
    delays = []
    for _ in range(9):
        before = datetime.now(timezone.utc)
        store.record_blocked('u', 'target_exists', firestore_client=client)
        delays.append(rows['u/builder']['v3_backoff_until'] - before)
    assert delays[0] <= timedelta(minutes=5, seconds=1)
    assert delays[1] > delays[0]
    assert max(delays) <= store.BLOCKED_BACKOFF_MAX + timedelta(seconds=1)
    assert rows['u/builder']['v3_blocked_reason'] == 'target_exists'
    assert store.backoff_until('u', firestore_client=client) == rows['u/builder']['v3_backoff_until']


def test_late_text_past_finished_at_extends_the_closure_window():
    row = source(
        finished_at=AT + timedelta(seconds=10),
        transcript_segments=[
            {'text': 'early', 'start': 0, 'end': 10},
            {'text': 'late text appended after completion', 'start': 3600, 'end': 3610},
        ],
    )
    assert store.speech_end(row) == AT + timedelta(seconds=3610)
    assert store.speech_end(source()) == AT + timedelta(seconds=10)


def test_adoptable_skips_deleted_tombstoned_and_recording_rows(monkeypatch):
    live = {'id': 'live', 'v3_derived': True}
    rows = {
        '/users/u/conversations/live': live,
        '/users/u/conversations/deleted': {'id': 'deleted', 'v3_derived': True, 'deleted': True},
        '/users/u/conversations/tomb': {'id': 'tomb', 'v3_derived': True},
        '/users/u/deleted_conversations/tomb': {'id': 'tomb'},
        '/users/u/conversations/rec': {'id': 'rec', 'recording': True},
        '/users/u/conversations/legacy': {'id': 'legacy'},
    }
    monkeypatch.setattr(store, 'decode_row', lambda uid, snap: {**snap.to_dict(), '_v3_revision': 1})
    found = store.adoptable(
        'u', ['live', 'deleted', 'tomb', 'rec', 'legacy', 'missing'], firestore_client=MemoryQuery(rows)
    )
    assert list(found) == ['live']
