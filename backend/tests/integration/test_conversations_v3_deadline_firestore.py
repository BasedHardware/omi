"""Exercise budget redelivery against durable v3 markers and real Firestore leases."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

from fastapi import Request
import pytest

from database import conversations_v3 as store, conversations_v3_leases as leases
from routers import conversations_v3_tasks as route
from tests.integration.test_conversations_v3_unchanged_writes_firestore import owner  # noqa: F401
from utils.conversations.v3 import budget, created, metrics, service


@pytest.fixture
def delivery(owner, monkeypatch):
    client, user = owner
    for module in (store, leases):
        monkeypatch.setattr(module, 'get_firestore_client', lambda: client)
    monkeypatch.setenv('CONVERSATIONS_V3_RECONCILE_DEADLINE', 'on')
    monkeypatch.setenv('CONVERSATIONS_V3_RECONCILE_BUDGET_SECONDS', '480')
    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_TITLE', 'off')
    monkeypatch.setattr(service.context, 'outline_sources', lambda *_: ({}, [], []))
    monkeypatch.setattr(service.visibility, 'hydrate_recognition', lambda *_: None)
    monkeypatch.setattr(service, 'enqueue', lambda *args, **kwargs: None)
    clock = [0]
    monkeypatch.setattr(budget, 'monotonic', lambda: clock[0])

    async def run():
        return await route.reconcile(route.ReconcileRequest(uid=user.id), Request({'type': 'http', 'headers': []}), 0)

    return user, clock, run


def assert_yield(response):
    assert response.status_code == 409
    assert json.loads(response.body) == {'status': 'retry', 'reason': 'policy_defer'}


@pytest.mark.asyncio
async def test_budget_keeps_completed_outline_and_pending_sources(delivery, monkeypatch):
    user, clock, run = delivery
    now = datetime.now(timezone.utc)
    refs = [user.collection('conversations').document(f'recording-{i}') for i in range(2)]
    for index, ref in enumerate(refs):
        start = now - timedelta(hours=4 - index)
        ref.set(
            {
                'id': ref.id,
                'recording': True,
                'source': 'omi',
                'status': 'completed',
                'started_at': start,
                'finished_at': start + timedelta(minutes=2),
                'v3_pending': True,
                'v3_pending_since': start,
                'data_protection_level': 'standard',
                'transcript_segments': [
                    {'id': ref.id, 'text': 'Synthetic planning speech ' * 40, 'start': 0, 'end': 120, 'is_user': True},
                ],
            }
        )

    calls = []

    def outline(_uid, messages):
        calls.append(messages)
        if len(calls) == 1:
            clock[0] += 410
        return json.dumps({'conversations': [{'first_line': 1, 'kind': 'conversation', 'title': 'Planning'}]})

    monkeypatch.setattr(service.models, 'outline', outline)
    monkeypatch.setattr(service, 'drain_processing', AsyncMock())

    def broken_metric(*_args):
        raise RuntimeError('metrics unavailable')

    monkeypatch.setattr(metrics.RECONCILE_BUDGET_YIELDS, 'labels', broken_metric)
    assert_yield(await run())
    assert len(calls) == 1
    assert all(ref.get().get('v3_pending') for ref in refs)
    assert leases.lease_ref(store.get_firestore_client(), user.id, 'builder').get().get('token') is None

    assert await run() == {'outcome': 'committed'}
    assert len(calls) == 2
    assert all(not ref.get().get('v3_pending') for ref in refs)


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [True, False])
async def test_budget_finishes_started_unit_and_resumes_at_next_row(delivery, monkeypatch, enabled):
    user, clock, run = delivery
    if not enabled:
        monkeypatch.setenv('CONVERSATIONS_V3_RECONCILE_DEADLINE', 'off')
    now = datetime.now(timezone.utc)
    coll = user.collection('conversations')
    for cid in ('a', 'b'):
        coll.document(cid).set(
            {
                'id': cid,
                'v3_derived': True,
                'v3_process_pending': True,
                'is_locked': True,
                'data_protection_level': 'standard',
                'started_at': now,
                'finished_at': now,
            }
        )

    calls = []
    process = service._process

    def finish(uid, row, token):
        calls.append(row['id'])
        if row['id'] == 'a':
            clock[0] += 490
        process(uid, row, token)

    monkeypatch.setattr(service, '_process', finish)
    monkeypatch.setattr(created, 'deliver', AsyncMock())

    result = await run()
    if enabled:
        assert_yield(result)
        assert calls == ['a']
        assert not coll.document('a').get().get('v3_process_pending')
        assert coll.document('b').get().get('v3_process_pending')
        lease = leases.lease_ref(store.get_firestore_client(), user.id, 'summary-a').get()
        assert lease.get('token') is None
        assert await run() == {'outcome': 'committed'}
    else:
        assert result == {'outcome': 'committed'}
    assert calls == ['a', 'b']
    assert not coll.document('b').get().get('v3_process_pending')
