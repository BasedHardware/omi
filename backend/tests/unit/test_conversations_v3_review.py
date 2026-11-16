"""Round-one regressions for bounded builder work and projected read surfaces."""

from database import conversations_v3_leases as leases

from datetime import datetime, timedelta, timezone
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from database import conversations_v3 as store
from utils.conversations.v3 import service
from utils import entity_pages
from database import conversations as conversations_db, mcp_conversation_pages
from utils.mcp_server.handlers import conversations as mcp_handlers

AT = datetime(2026, 11, 16, tzinfo=timezone.utc)


def source(cid='r', **updates):
    return {
        'id': cid,
        'recording': True,
        'status': 'completed',
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=10),
        'v3_pending': True,
        'transcript_segments': [{'text': 'speech for a synthetic plan', 'start': 0, 'end': 10}],
        **updates,
    }


@pytest.fixture
def builder(monkeypatch):
    committed, messages = [], []

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(leases, 'acquire', lambda *a: 'token')
    monkeypatch.setattr(leases, 'renew', lambda *a: None)
    monkeypatch.setattr(leases, 'release', lambda *a: None)
    monkeypatch.setattr(store, 'outline_attempt', lambda *a: True)
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: committed.append(a))
    monkeypatch.setattr(service, 'has_pending', lambda *a: False)
    monkeypatch.setattr(service, 'enqueue', lambda *a, **kw: None)
    monkeypatch.setattr(service, 'drain_processing', AsyncMock())

    def model(uid, prompt):
        messages.append(prompt)
        return '{"conversations":[{"first_line":1,"title":"A plan","line":"You made a plan.","kind":"conversation"}]}'

    monkeypatch.setattr(service.models, 'outline', model)
    return committed, messages


@pytest.mark.asyncio
async def test_on_open_scopes_load_and_queues_processing(builder, monkeypatch):
    committed, _ = builder
    seen = []
    prior = {
        'id': 'c',
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=10),
        'status': 'in_progress',
        'v3_recording_ids': ['r'],
    }

    def load(uid, **kw):
        seen.append(kw)
        return {'r': source()}, {'c': prior}, []

    monkeypatch.setattr(store, 'load', load)
    await service.reconcile('u', on_open=True, conversation_id='c')
    assert seen == [{'conversation_id': 'c'}]
    service.drain_processing.assert_not_awaited()
    assert committed


@pytest.mark.asyncio
async def test_unreadable_markers_are_committed_instead_of_blocking(builder, monkeypatch):
    committed, _ = builder
    monkeypatch.setattr(
        store,
        'load',
        lambda *a, **kw: (
            {
                'private': source('private', data_protection_level='private'),
                'clockless': source('clockless', started_at=None),
            },
            {},
            [],
        ),
    )
    await service.reconcile('u')
    assert set(committed[0][2]) == {'private', 'clockless'}
    assert committed[0][4] == []


@pytest.mark.asyncio
async def test_preceding_outline_context_is_title_and_line(builder, monkeypatch):
    _, messages = builder
    a, b = source('a'), source(
        'b',
        started_at=AT + timedelta(minutes=10),
        finished_at=AT + timedelta(minutes=11),
        transcript_segments=[{'text': 'another synthetic discussion', 'start': 0, 'end': 10}],
    )
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'a': a_row, 'b': b_row}, {}, []))
    a_row, b_row = a, b
    await service.reconcile('u')
    assert messages[1][-1] == ('human', 'Preceding conversation: A plan\nYou made a plan.')


@pytest.mark.asyncio
async def test_malformed_outline_uses_cached_deterministic_fallback(builder, monkeypatch):
    committed, _ = builder
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    monkeypatch.setattr(service.models, 'outline', lambda *a: 'malformed JSON')
    await service.reconcile('u')
    cache = committed[0][5]
    assert cache[0]['entries'][0]['first_line'] == 1
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, cache))
    monkeypatch.setattr(service.models, 'outline', lambda *a: pytest.fail('paid malformed retry'))
    await service.reconcile('u')


@pytest.mark.parametrize('recording,hidden', [(True, False), (False, True)])
def test_home_projection_retains_visibility_fields(recording, hidden):
    from database import home_feed

    row = {
        'id': 'c',
        'recording': recording,
        'home_hidden': hidden,
        'status': 'completed',
        'discarded': False,
        'structured': {'title': 'Plan'},
    }
    projected = {k: v for k, v in row.items() if k in home_feed.CONVERSATION_FIELDS}
    assert not home_feed._visible(projected)


def test_mcp_projection_rejects_recording_but_keeps_hidden_conversation():
    from database.mcp_read_queries import MCP_CONVERSATION_CARD_FIELD_PATHS
    from database.conversations import is_visible_conversation

    for recording in (True, False):
        row = {'recording': recording, 'home_hidden': True, 'status': 'completed', 'discarded': False}
        projected = {k: v for k, v in row.items() if k in MCP_CONVERSATION_CARD_FIELD_PATHS}
        assert is_visible_conversation(projected) is not recording


def test_people_stats_projection_rejects_recording():
    from database.conversation_scan import PEOPLE_STATS_FIELD_PATHS
    from database.conversations import is_visible_conversation

    row = {'recording': True, 'status': 'completed', 'discarded': False}
    projected = {k: v for k, v in row.items() if k in PEOPLE_STATS_FIELD_PATHS}
    assert not is_visible_conversation(projected)


class MemoryQuery:
    def __init__(self, rows, path='', filters=(), orders=(), cap=None, after=None, calls=None, projection=None):
        self.rows, self.path, self.filters = rows, path, filters
        self.orders, self.cap, self.after = orders, cap, after
        self.calls = calls if calls is not None else []
        self.projection = projection

    def copy(self, **kw):
        return MemoryQuery(
            **(
                dict(
                    rows=self.rows,
                    path=self.path,
                    filters=self.filters,
                    orders=self.orders,
                    cap=self.cap,
                    after=self.after,
                    calls=self.calls,
                    projection=self.projection,
                )
                | kw
            )
        )

    def collection(self, name):
        return self.copy(path=self.path + '/' + name)

    def collection_group(self, name):
        return self.copy(path='*' + name)

    def document(self, name):
        return self.copy(path=self.path + '/' + name)

    def get(self):
        from types import SimpleNamespace

        data = self.rows.get(self.path)
        if data is not None and self.projection is not None:
            roots = {p.split('.')[0] for p in self.projection}
            data = {k: v for k, v in data.items() if k in roots}
        return SimpleNamespace(
            id=self.path.rsplit('/', 1)[-1],
            exists=data is not None,
            update_time=1,
            reference=SimpleNamespace(path=self.path.lstrip('/')),
            to_dict=lambda: deepcopy(data),
        )

    def select(self, fields):
        return self.copy(projection=fields)

    def get_all(self, refs, field_paths=None):
        return [ref.copy(projection=field_paths).get() for ref in refs]

    def where(self, *, filter):
        return self.copy(filters=self.filters + ((filter.field_path, filter.op_string, filter.value),))

    def limit(self, value):
        return self.copy(cap=value)

    def order_by(self, key, direction=None):
        return self.copy(orders=self.orders + (key,))

    def start_after(self, snapshot):
        return self.copy(after=snapshot.reference.path)

    def stream(self):
        self.calls.append((self.filters, self.cap, self.after))
        result = []
        for path, row in self.rows.items():
            if self.path.startswith('*'):
                if path.split('/')[-2] != self.path[1:]:
                    continue
            elif not path.startswith(self.path + '/') or path.count('/') != self.path.count('/') + 1:
                continue

            def matches():
                for field, op, expected in self.filters:
                    actual = row.get(field)
                    if actual is None:
                        return False
                    if not {
                        '==': lambda: actual == expected,
                        '>=': lambda: actual >= expected,
                        '<=': lambda: actual <= expected,
                    }[op]():
                        return False
                return True

            if matches() and all(k == '__name__' or k in row for k in self.orders):
                result.append(self.copy(path=path).get())

        def key(doc):
            row = doc.to_dict()
            return tuple(doc.reference.path if k == '__name__' else row[k] for k in self.orders)

        result.sort(key=key)
        if self.after:
            after_index = next(i for i, doc in enumerate(result) if doc.reference.path == self.after)
            result = result[after_index + 1 :]
        return iter(result[: self.cap])


def test_backlog_over_128_advances_pages_and_extends_prior_window(monkeypatch):
    from utils.conversations.v3 import outline, planner

    rows = {
        '/users/u/conversations/'
        + str(i): source(
            str(i),
            started_at=AT + timedelta(seconds=i * 12),
            finished_at=AT + timedelta(seconds=i * 12 + 10),
            v3_pending_since=AT + timedelta(seconds=i),
            transcript_segments=[{'text': f'synthetic speech number {i}', 'start': 0, 'end': 10}],
        )
        for i in range(129)
    }
    client = MemoryQuery(rows)
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a: False)
    monkeypatch.setattr(
        store, 'decode_row', lambda uid, snap: {**snap.to_dict(), '_v3_revision': 1} if snap.exists else None
    )
    existing_id = None
    processed = set()
    for _ in range(8):
        recordings, existing, _ = store.load('u', firestore_client=client)
        pending = {rid for rid, row in recordings.items() if row.get('v3_pending')}
        if not pending:
            break
        assert len(pending) <= 32
        assert min(pending, key=int) == str(len(processed))
        groups = outline.stretches(list(recordings.values()), AT + timedelta(hours=2))
        windows = planner.preserve_finished_windows(
            planner.windows(groups, [outline.fallback(g) for g in groups]), existing, recordings
        )
        prior = existing.get(existing_id)
        built = planner.build('u', windows[0], recordings, prior)
        if existing_id:
            assert built['id'] == existing_id
        existing_id = built['id']
        rows['/users/u/conversations/' + existing_id] = built
        for rid in pending:
            rows['/users/u/conversations/' + rid]['v3_pending'] = False
        processed.update(pending)
    assert len(processed) == 129
    assert len(rows['/users/u/conversations/' + existing_id]['transcript_segments']) == 129


@pytest.mark.asyncio
async def test_sweeper_filters_age_in_query_and_cursors_past_1000(monkeypatch):
    rows = {
        '/users/young/conversations/' + str(i): source(str(i), v3_pending_since=datetime.now(timezone.utc))
        for i in range(1000)
    }
    rows.update(
        {
            '/users/old' + str(i) + '/conversations/r': source(v3_pending_since=AT - timedelta(days=2))
            for i in range(1001)
        }
    )
    client = MemoryQuery(rows)

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    enqueued = []
    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(service, 'enqueue', lambda uid: enqueued.append(uid))
    assert await service.sweep() == 1001
    assert 'young' not in enqueued
    pending = [call for call in client.calls if any(f[0] == 'v3_pending_since' for f in call[0])]
    assert len(pending) == 2 and pending[1][2] is not None


@pytest.mark.parametrize('surface', ['mcp_list', 'developer_list', 'mcp_by_id', 'entity_page'])
def test_projected_product_surfaces_exclude_recordings(monkeypatch, surface):
    rows = {
        '/users/u/conversations/'
        + cid: dict(
            id=cid,
            recording=recording,
            home_hidden=True,
            status='completed',
            discarded=False,
            created_at=AT,
            started_at=AT,
            finished_at=AT,
            structured={'title': cid},
        )
        for cid, recording in [('recording', True), ('hidden-talk', False)]
    }
    client = MemoryQuery(rows)
    monkeypatch.setattr(mcp_conversation_pages, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(mcp_conversation_pages, '_bounded_read_cap', lambda *a: None)
    if surface == 'mcp_by_id':
        result = conversations_db.get_mcp_conversations_by_id(
            'u', ['recording', 'hidden-talk'], include_transcript=False, firestore_client=client
        )
    elif surface == 'entity_page':
        monkeypatch.setattr(entity_pages.store, 'user', lambda uid: client.collection('users').document(uid))
        result = list(entity_pages._entity_page_conversation_page('u').values())
    else:
        result, _ = mcp_handlers.conversation_cards_page_core('u', limit=10, cursor_kind=surface)
    assert [r['id'] for r in result] == ['hidden-talk']


@pytest.mark.asyncio
async def test_exhausted_outline_budget_does_not_count_a_paid_call(builder, monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    monkeypatch.setattr(store, 'outline_attempt', lambda *a: False)
    monkeypatch.setattr(service.models, 'outline', lambda *a: pytest.fail('spent exhausted outline budget'))
    meter = MagicMock()
    monkeypatch.setattr(service.metrics, 'MODEL_CALLS', meter)
    await service.reconcile('u')
    meter.labels.assert_not_called()


def test_synchronous_writer_owns_and_joins_lease_heartbeat(monkeypatch):
    import threading

    calls, renewed = [], threading.Event()
    monkeypatch.setattr(leases, 'LEASE_SECONDS', 0.003)

    def renew(*args):
        calls.append(args)
        renewed.set()

    monkeypatch.setattr(leases, 'renew', renew)
    with leases.keepalive('u', 'summary-c', 'token'):
        assert renewed.wait(1)
    assert calls and all(c == ('u', 'summary-c', 'token') for c in calls)
    assert not any(t.name == 'v3-writer-lease' for t in threading.enumerate())
