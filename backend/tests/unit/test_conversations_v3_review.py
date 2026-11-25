"""Round-one regressions for bounded builder work and projected read surfaces."""

from database import conversations_v3_leases as leases

from datetime import datetime, timedelta, timezone
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from database import conversations_v3 as store
from database import conversations_v3_backfill_runs as runs
from utils.conversations.v3 import service
from utils.conversations import process_conversation as process_pipeline
from utils.conversations import merge_conversations as merger
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
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(leases, 'acquire', lambda *a, promote_llm=False: 'token')
    monkeypatch.setattr(leases, 'renew', lambda *a: None)
    monkeypatch.setattr(leases, 'release', lambda *a: None)
    monkeypatch.setattr(store, 'outline_attempt', lambda *a, **kw: True)
    monkeypatch.setattr(store, 'save_outline', lambda *a, **kw: None)
    monkeypatch.setattr(store, 'adoptable', lambda *a: {})
    monkeypatch.setattr(store, 'merge_donors_have_tasks', lambda *a, **kw: False)
    monkeypatch.setattr(store, 'backoff_state', lambda *a: (None, None))
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
async def test_same_start_fresh_windows_get_distinct_ids_and_audio(builder, monkeypatch):
    from uuid import NAMESPACE_URL, uuid5

    committed, _ = builder
    prior_id = str(uuid5(NAMESPACE_URL, f'v3:u:{AT.isoformat()}'))
    prior_end = AT + timedelta(seconds=10)
    prior = {'id': prior_id, 'status': 'completed', 'started_at': AT, 'finished_at': prior_end}
    recording = source(
        claims=[{'conversation_id': prior_id, 'start': AT, 'end': prior_end}],
        audio_files=[{'id': 'f', 'duration': 14}],
        transcript_segments=[
            {'id': 'first', 'text': 'one ' * 300, 'start': 0, 'end': 12},
            {'id': 'second', 'text': 'two ' * 300, 'start': 0, 'end': 14},
        ],
    )
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': recording}, {prior_id: prior}, []))
    monkeypatch.setattr(
        service.models,
        'outline',
        lambda *a: '{"conversations":[{"first_line":1,"title":"One","kind":"conversation"},'
        '{"first_line":2,"title":"Two","kind":"conversation"}]}',
    )

    await service.reconcile('u')
    rows = committed[0][4]
    assert len({prior_id, *(row['id'] for row in rows)}) == 3
    assert [[(p['start'], p['end']) for p in row['recording_pieces']] for row in rows] == [[(10, 12)], [(12, 14)]]


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
async def test_malformed_outline_is_published_but_not_cached_and_open_retries(builder, monkeypatch):
    from utils.conversations.v3 import summary

    committed, _ = builder
    recording = source()
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': recording}, {}, []))
    monkeypatch.setattr(service.context, 'cache_key', lambda *a: 'fingerprint')
    malformed = AsyncMock(return_value='malformed JSON')
    with monkeypatch.context() as patch:
        patch.setattr(service, 'leased_work', malformed)
        await service.reconcile('u')
    (row,) = committed[0][4]
    assert not committed[0][5]
    assert row['v3_process_failure_reason'] == 'outline'
    assert summary.needs_open_reconcile(row)
    old_cache = [{'fingerprint': 'fingerprint', 'entries': [{'first_line': 1, '_outline_failed': True}]}]
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': recording}, {row['id']: row}, old_cache))
    await service.reconcile('u', on_open=True, promote_llm=True, conversation_id=row['id'])
    (cache_entry,) = committed[1][5]
    assert cache_entry['entries'][0]['title'] == 'A plan'
    assert not cache_entry['entries'][0].get('_outline_failed')
    assert committed[1][4][0]['v3_process_pending'] is True


@pytest.mark.parametrize(
    'error, status',
    [('v3_lease_lifetime_exhausted', 200), ('v3_lease_lifetime_exhausted unexpectedly', 500)],
)
def test_reconcile_route_falls_back_only_for_exact_lease_exhaustion(builder, monkeypatch, error, status):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import conversations_v3_tasks as routes

    committed, _ = builder
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, []))
    paid_work = AsyncMock(side_effect=RuntimeError(error))
    monkeypatch.setattr(service, 'leased_work', paid_work)
    fallback = service.metrics.RECONCILES.labels('outline_fallback')
    before = fallback._value.get()
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.verify_cloud_tasks_oidc] = lambda: 0

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/v1/conversations-v3/reconcile', json={'uid': 'u'})

    paid_work.assert_awaited_once()
    assert response.status_code == status
    if status == 200:
        assert response.json() == {'outcome': 'committed'}
        (commit,) = committed
        assert commit[4]
        assert not commit[5]
        assert fallback._value.get() == before + 1
    else:
        assert not committed
        assert fallback._value.get() == before


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
                        'in': lambda: actual in expected,
                        '>': lambda: actual > expected,
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


@pytest.mark.parametrize('bound,eligible,expected', [(True, True, True), (False, True, False), (True, False, False)])
def test_recognition_uses_segment_bound_policy_evidence(monkeypatch, bound, eligible, expected):
    from models.speaker_evidence import SpeakerEvidence
    from utils.speakers import evidence
    from utils.conversations.v3 import visibility

    row = source(transcript_segments=[{'id': 's', 'text': 'synthetic words', 'is_user': False}])
    packet = SpeakerEvidence(
        status='resolved',
        policy_version='test',
        clusters=[
            {
                'id': 'v',
                'segment_ids': ['s' if bound else 'stale'],
                'candidates': [
                    {
                        'person_id': 'owner',
                        'probability': 1,
                        'band': 'confident',
                        'source': 'voice',
                        'label_eligible': eligible,
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr(evidence, 'get_evidence', lambda *a: packet)
    visibility.hydrate_recognition('u', {'r': row}, [{'kind': 'background', 'lines': [{'conversation_id': 'r'}]}])
    assert row['_v3_wearer_recognized'] is expected


@pytest.mark.asyncio
async def test_uncertain_visibility_counter_counts_committed_first_exposure(builder, monkeypatch):
    from unittest.mock import MagicMock
    from utils.speakers import evidence

    committed, _ = builder
    monkeypatch.setattr(evidence, 'get_evidence', lambda *a: None)
    monkeypatch.setattr(
        store,
        'load',
        lambda *a, **kw: (
            {
                'r': source(
                    transcript_segments=[{'id': 's', 'text': 'speech ' * 300, 'start': 0, 'end': 10, 'is_user': False}]
                )
            },
            {},
            [],
        ),
    )
    monkeypatch.setattr(
        service.models,
        'outline',
        lambda *a: '{"conversations":[{"first_line":1,"title":"A plan","line":"A plan.","kind":"background"}]}',
    )
    meter = MagicMock()
    monkeypatch.setattr(service.metrics, 'UNCERTAIN_SHOWN', meter)
    await service.reconcile('u')
    result = committed[0][4][0]
    assert result['kind'] == 'conversation' and not result['home_hidden']
    prior = dict(result, status='completed')
    monkeypatch.setattr(
        store,
        'load',
        lambda *a, **kw: (
            {
                'r': source(
                    transcript_segments=[{'id': 's', 'text': 'speech ' * 300, 'start': 0, 'end': 10, 'is_user': False}]
                )
            },
            {prior['id']: prior},
            [],
        ),
    )
    await service.reconcile('u')
    meter.inc.assert_called_once()


@pytest.mark.parametrize(
    'text,manual,backfilled,expect_notes,expected_floor',
    [
        ('speech ' * 40, True, False, True, None),
        ('speech ' * 40, True, True, True, None),
        ('界' * 19, False, False, False, (True, True)),
        ('界' * 20, False, False, True, (True, False)),
        ('あ' * 19, False, False, False, (True, True)),
        ('あ' * 20, False, False, True, (True, False)),
        ('界' * 20, False, True, True, None),
    ],
)
def test_process_applies_word_floor_to_automatic_windows(
    monkeypatch, text, manual, backfilled, expect_notes, expected_floor
):
    from utils.conversations import process_conversation as process, lifecycle
    from types import SimpleNamespace
    from database import conversations_v3_processing as writers

    row = {
        'id': 'window',
        'v3_derived': True,
        'backfilled': backfilled,
        'manual_end': manual,
        'kind': 'conversation',
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT,
        'structured': {},
        'transcript_segments': [{'text': text, 'start': 0, 'end': 10, 'is_user': False}],
    }
    called, completed, settlements = [], [], []
    monkeypatch.setattr(writers, 'begin_processing', lambda *a, **kw: True)
    monkeypatch.setattr(writers, 'settle_processing', lambda *a, **kw: settlements.append(kw))
    monkeypatch.setattr(lifecycle, 'complete', lambda _uid, cid: completed.append(cid))

    def full(uid, language, conversation, **kw):
        called.append((conversation.id, conversation.manual_end, conversation.transcript_segments[0].text))
        kw['persistence_observer'](True)
        return SimpleNamespace(status='completed')

    monkeypatch.setattr(process, 'process_conversation', full)
    service._process('u', row, 'token')
    assert called == ([('window', manual, text)] if expect_notes else [])
    assert completed == ([] if expect_notes else ['window'])
    assert settlements[0]['word_floor_outcomes'] == expected_floor


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['transcription', 'outline'])
async def test_builder_terminal_failure_is_visible_and_retryable(builder, monkeypatch, failure):
    committed, _ = builder
    row = source(
        status='failed' if failure == 'transcription' else 'completed',
        transcript_segments=[{'text': 'speech ' * 300, 'start': 0, 'end': 10, 'is_user': True}],
    )
    monkeypatch.setattr(store, 'load', lambda *a, **k: ({'r': row}, {}, []))
    if failure == 'outline':
        monkeypatch.setattr(store, 'outline_attempt', lambda *a: False)
    await service.reconcile('u')
    built = committed[0][4][0]
    assert built['status'] == 'completed' and built['tile_state'] == 'failed'
    assert built['summary_retryable'] and not built['v3_process_pending']
    assert not built['home_hidden']


def test_merge_stub_preserves_manual_intent_even_without_requested_reprocess(monkeypatch):
    class Captured(BaseException):
        pass

    rows = {
        cid: {
            'id': cid,
            'v3_derived': True,
            'manual_end': cid == 'a',
            'status': 'completed',
            'started_at': AT + timedelta(seconds=i * 20),
            'created_at': AT,
            'finished_at': AT + timedelta(seconds=i * 20 + 10),
            'structured': {'title': cid},
            'transcript_segments': [
                {'id': cid + '-s', 'text': 'A synthetic short plan.', 'start': 0, 'end': 10, 'is_user': True}
            ],
        }
        for i, cid in enumerate(('a', 'b'))
    }
    monkeypatch.setattr(merger.conversations_db, 'get_conversation', lambda uid, cid: rows[cid])
    monkeypatch.setattr(merger, '_collect_all_photos', lambda *a: [])
    captured = []

    def stub(uid, payload):
        captured.append(payload)
        raise Captured()

    monkeypatch.setattr(merger.lifecycle_service, 'create_processing_conversation', stub)
    with pytest.raises(Captured):
        merger.perform_merge_async('u', ['a', 'b'], reprocess=False)
    assert captured[0]['manual_end'] is True and not captured[0]['home_hidden']
    assert captured[0]['tile_state'] == 'writing'  # intent forces the full notes path next


@pytest.mark.asyncio
async def test_late_manual_end_owes_full_notes_even_without_new_words(builder, monkeypatch):
    committed, _ = builder
    transcript = [{'text': 'speech ' * 40, 'start': 0, 'end': 10, 'is_user': True}]
    prior = {
        'id': 'c',
        'v3_derived': True,
        'status': 'completed',
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=10),
        'home_hidden': True,
        'kind': 'conversation',
        'v3_recording_ids': ['r'],
        'transcript_segments': transcript,
        'summary_covers_through': AT + timedelta(seconds=10),
        'tile_state': 'done',
    }
    monkeypatch.setattr(
        store,
        'load',
        lambda *a, **k: ({'r': source(v3_manual_end=True, transcript_segments=transcript)}, {'c': prior}, []),
    )
    await service.reconcile('u')
    row = committed[0][4][0]
    assert row['manual_end'] and not row['home_hidden']
    assert row['v3_process_pending'] and row['tile_state'] == 'writing'
    assert row['summary_covers_through'] is None


@pytest.mark.asyncio
async def test_transcription_failure_does_not_wait_for_silence_deadline(builder, monkeypatch):
    from datetime import datetime

    committed, _ = builder

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return AT + timedelta(seconds=11)

    monkeypatch.setattr(service, 'datetime', Clock)
    monkeypatch.setattr(
        store,
        'load',
        lambda *a, **k: (
            {
                'r': source(
                    status='failed',
                    v3_manual_end=False,
                    transcript_segments=[{'text': 'speech ' * 300, 'start': 0, 'end': 10, 'is_user': True}],
                )
            },
            {},
            [],
        ),
    )
    await service.reconcile('u')
    row = committed[0][4][0]
    assert row['tile_state'] == 'failed' and row['status'] == 'completed' and row['summary_retryable']


@pytest.mark.parametrize('count', [20, 40])
def test_hour_long_continuous_talk_crosses_anchor_and_pending_page(monkeypatch, count):
    from utils.conversations.v3 import outline, planner

    rows = {
        '/users/u/conversations/'
        + str(i): source(
            str(i),
            started_at=AT + timedelta(seconds=i * 180),
            finished_at=AT + timedelta(seconds=i * 180 + 10),
            v3_pending_since=AT + timedelta(seconds=i),
            transcript_segments=[{'text': f'synthetic speech number {i}', 'start': 0, 'end': 10}],
        )
        for i in range(count)
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
    assert len(processed) == count
    assert len(rows['/users/u/conversations/' + existing_id]['transcript_segments']) == count


@pytest.mark.parametrize('next_minute', [100, 103])
def test_page_continuation_uses_capture_chronology_not_pending_order(monkeypatch, next_minute):
    rows = {}
    for i in range(33):
        minute = 100 if i == 0 else 0 if i == 31 else next_minute if i == 32 else i * 3
        rows['/users/u/conversations/' + str(i)] = source(
            str(i),
            started_at=AT + timedelta(minutes=minute),
            finished_at=AT + timedelta(minutes=minute, seconds=10),
            v3_pending_since=AT + timedelta(seconds=i),
        )
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a: False)
    monkeypatch.setattr(
        store, 'decode_row', lambda uid, snap: dict(snap.to_dict(), _v3_revision=1) if snap.exists else None
    )
    recordings, _, _ = store.load('u', firestore_client=MemoryQuery(rows))
    assert recordings['0']['_v3_page_continues']
    assert not recordings['31'].get('_v3_page_continues')
    assert len(recordings) == 32


@pytest.mark.asyncio
async def test_missing_transcript_blob_is_unreadable_and_settles_without_a_window(builder, monkeypatch):
    from database.transcript_pointer import TranscriptBlobAbsent

    committed, _ = builder
    client = MemoryQuery({'/users/u/conversations/r': source(v3_pending_since=AT)})
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a: False)
    monkeypatch.setattr(
        store.conversations,
        'decode_transcript_segments_verified',
        lambda *a: (_ for _ in ()).throw(TranscriptBlobAbsent('gone')),
    )
    await service.reconcile('u')
    assert committed[0][2]['r']['_v3_unreadable']
    assert committed[0][4] == []


@pytest.mark.asyncio
async def test_processing_and_purge_sweeps_cursor_past_errors_and_1000_rows(monkeypatch):
    rows = {}
    for i in range(1001):
        rows[f'/users/u{i:04}/conversations/process'] = {'v3_process_pending': True}
        rows[f'/users/u{i:04}/conversations/purge'] = {'v3_audio_purge_pending': True}
    client = MemoryQuery(rows)

    async def blocking(pool, fn, *args, **kw):
        return fn(*args, **kw)

    enqueued, purged, retries = [], [], []

    def purge(uid, cid):
        purged.append(uid)
        if uid == 'u0000':
            raise OSError('synthetic transient storage error')

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(service, 'enqueue', lambda uid: enqueued.append(uid))
    monkeypatch.setattr(service, 'purge_audio', purge)
    monkeypatch.setattr(service.conversations_db, 'update_conversation', lambda *a: retries.append(a))
    assert await service.sweep() == 1001
    assert len(enqueued) == len(purged) == 1001
    assert retries[0][2]['v3_audio_purge_pending']
    assert retries[0][2]['v3_audio_purge_attempts'] == 1
    for field in ['v3_process_pending', 'v3_audio_purge_pending']:
        pages = [c for c in client.calls if any(f[0] == field for f in c[0])]
        assert len(pages) == 2 and pages[1][2] is not None


def _rotation_rows(successor, rotated=True):
    rows = {
        '/users/u/conversations/a': source(
            'a',
            started_at=AT,
            finished_at=AT + timedelta(seconds=150),
            v3_pending=False,
            v3_pending_since=None,
            **({'v3_rotation_cap_seconds': 240.0} if rotated else {}),
        ),
        '/users/u/conversations/x': {'id': 'x', 'v3_derived': True, 'started_at': AT + timedelta(seconds=1)},
    }
    if successor:
        rows['/users/u/conversations/b'] = {
            'id': 'b',
            'recording': True,
            'v3_pending': False,
            'started_at': AT + timedelta(seconds=150),
            'created_at': AT + timedelta(seconds=150),
            **successor,
        }
    return rows


@pytest.mark.parametrize(
    ('successor', 'now_after', 'continues'),
    [
        ({'status': 'in_progress'}, 200, True),  # still capturing, before the rotation cap
        ({'status': 'in_progress'}, 150 + 255 + 1, False),  # live past the cap: it has heard no speech
        ({'status': 'processing', 'finished_at': AT + timedelta(seconds=300)}, 600, True),  # sealed, untranscribed
        ({'status': 'processing', 'finished_at': AT + timedelta(seconds=300)}, 300 + 901, False),  # bounded wait
        ({'status': 'completed'}, 600, False),  # transcribed with no lines: real silence
        ({'status': 'in_progress', 'started_at': AT + timedelta(minutes=8)}, 500, False),  # after a 5 min gap
        (None, 400, False),
    ],
)
def test_untranscribed_successor_keeps_the_stretch_open(monkeypatch, successor, now_after, continues):
    _assert_successor(monkeypatch, _rotation_rows(successor), now_after, continues)


@pytest.mark.parametrize('successor', [{'status': 'in_progress'}, {'status': 'processing'}])
def test_a_recording_rotation_did_not_seal_keeps_the_five_minute_rule(monkeypatch, successor):
    # Rotation off (or a quiet seal): no cap stamp, so the builder behaves exactly as before.
    _assert_successor(monkeypatch, _rotation_rows(successor, rotated=False), 200, False)


def _assert_successor(monkeypatch, rows, now_after, continues):
    from utils.conversations.v3 import outline

    now = AT + timedelta(seconds=now_after)
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a: False)
    monkeypatch.setattr(
        store, 'decode_row', lambda uid, snap: dict(snap.to_dict(), _v3_revision=1) if snap.exists else None
    )
    monkeypatch.setattr(store, 'datetime', type('Clock', (datetime,), {'now': staticmethod(lambda tz=None: now)}))
    recordings = {'a': store.recording_input('u', MemoryQuery(rows).document('users/u/conversations/a').get())}
    store._mark_successor_pending(
        MemoryQuery(rows).collection('users').document('u').collection('conversations'), recordings
    )
    assert bool(recordings['a'].get('_v3_page_continues')) is continues
    groups = outline.stretches(list(recordings.values()), AT + timedelta(minutes=30))
    assert groups[0]['finished'] is not continues


def test_rotated_recordings_stitch_into_one_stretch_in_order():
    from utils.conversations.v3 import outline, planner

    def piece(cid, offset, text):
        return source(
            cid,
            started_at=AT + timedelta(seconds=offset),
            finished_at=AT + timedelta(seconds=offset + 150),
            transcript_segments=[{'text': text, 'start': 1, 'end': 149}],
        )

    members = [piece('r2', 150, 'second part'), piece('r1', 0, 'first part'), piece('r3', 300, 'third part')]
    groups = outline.stretches(members, AT + timedelta(minutes=20))
    assert len(groups) == 1 and groups[0]['finished']
    assert [line['text'] for line in groups[0]['lines']] == ['first part', 'second part', 'third part']
    entries = [[{'first_line': 1, 'title': 'T', 'line': '', 'kind': 'conversation', 'people': [], 'sections': []}]]
    (window,) = planner.windows(groups, entries)
    row = planner.build('u', window, {m['id']: m for m in members})
    assert row['v3_recording_ids'] == ['r1', 'r2', 'r3']


@pytest.mark.asyncio
@pytest.mark.parametrize('on_open', [True, False])
async def test_configured_lock_is_bypassed_by_open_and_manual_end(builder, monkeypatch, on_open):
    committed, _ = builder
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    start = datetime.now(timezone.utc) - timedelta(seconds=30)
    end = start + timedelta(seconds=10)
    prior = {
        'id': 'card',
        'started_at': start,
        'finished_at': end,
        'status': 'in_progress',
        'v3_unlocked': True,
        'v3_recording_ids': ['r'],
    }
    raw = source(started_at=start, finished_at=end, v3_manual_end=not on_open)
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': raw}, {'card': prior}, []))
    await service.reconcile('synthetic', on_open=on_open, conversation_id='card' if on_open else None)
    (row,) = committed[0][4]
    assert row['id'] == 'card' and row['status'] == 'processing'
    assert not row.get('v3_unlocked')
    assert row['v3_process_pending']
    assert row['manual_end'] is not on_open
    assert bool(row.get('v3_open_locked')) is on_open


@pytest.mark.asyncio
@pytest.mark.parametrize('insert_before_preview', [False, True])
async def test_configured_preview_reuses_outline_at_lock(builder, monkeypatch, insert_before_preview):
    committed, messages = builder
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    start = datetime.now(timezone.utc) - timedelta(minutes=10)
    end = start + timedelta(seconds=10)
    raw = source(
        started_at=start,
        finished_at=end,
        transcript_segments=[{'text': 'synthetic ' * 310, 'start': 4, 'end': 10}],
    )
    inputs = [{'r': raw}, {}, []]
    monkeypatch.setattr(store, 'load', lambda *a, **kw: inputs)
    await service.reconcile('synthetic')
    (preview,) = committed[-1][4]
    assert preview['v3_unlocked'] and not preview.get('v3_process_pending')
    assert preview['structured']['title'] == 'A plan'
    assert preview['tile_state'] == 'live' and len(messages) == 1

    inputs[1] = {preview['id']: preview}
    inputs[2] = committed[-1][5]
    if insert_before_preview:
        raw['transcript_segments'].insert(0, {'text': 'revised prefix', 'start': 0, 'end': 2})
    else:
        raw['transcript_segments'].append({'text': 'revised tail', 'start': 11, 'end': 12})
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '301')
    await service.reconcile('synthetic')
    (locked,) = committed[-1][4]
    assert locked['id'] == preview['id'] and not locked.get('v3_unlocked')
    assert locked['v3_process_pending'] and len(messages) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('donor_has_tasks', [False, True])
async def test_configured_reconcile_refines_locked_cards_without_new_notes(builder, monkeypatch, donor_has_tasks):
    from tests.unit.test_conversations_v3_lock_timing import _locked_pair

    committed, _ = builder
    _window, existing, recordings = _locked_pair(datetime.now(timezone.utc) - timedelta(hours=2))
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    recordings['r'].update(recording=True, status='completed', v3_pending=True)
    monkeypatch.setattr(store, 'load', lambda *a, **kw: (recordings, existing, []))
    monkeypatch.setattr(store, 'merge_donors_have_tasks', lambda *a, **kw: donor_has_tasks)
    assert await service.reconcile('synthetic') == 'committed'
    if donor_has_tasks:
        assert {row['id'] for row in committed[0][4]} == {'early', 'late'}
        assert all(not row.get('_v3_absorbed') for row in committed[0][4])
        return
    (row,) = committed[0][4]
    assert row['id'] == 'early' and row['_v3_absorbed'] == ['late']
    assert row['summary_covers_through'] == row['finished_at']
    assert not row.get('v3_process_pending')


def test_builder_loads_indexed_provisional_card_without_pending_audio(monkeypatch):
    prefix = '/users/synthetic/'
    rows = {
        prefix + 'conversation_v3_leases/builder': {'unlocked_ids': ['older', 'removed']},
        prefix
        + 'conversations/older': {
            'id': 'older',
            'v3_derived': True,
            'v3_unlocked': True,
            'status': 'processing',
            'started_at': AT,
            'finished_at': AT + timedelta(seconds=10),
            'v3_recording_ids': ['r'],
        },
        prefix + 'conversations/r': source(v3_pending=False),
    }
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a, **kw: False)
    monkeypatch.setattr(store, 'decode_row', lambda uid, snap: snap.to_dict() if snap.exists else None)
    monkeypatch.setattr(store, 'recording_input', lambda uid, snap: snap.to_dict() if snap.exists else None)
    recordings, existing, _ = store.load('synthetic', firestore_client=MemoryQuery(rows))
    assert set(existing) == {'older'} and set(recordings) == {'r'}


@pytest.mark.asyncio
async def test_one_hour_lock_leaves_only_the_last_stretch_open(builder, monkeypatch):
    committed, _ = builder
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    start = datetime.now(timezone.utc) - timedelta(seconds=490)
    raw = source(
        started_at=start,
        finished_at=start + timedelta(seconds=490),
        transcript_segments=[
            {'text': 'first ' * 310, 'start': 0, 'end': 10},
            {'text': 'second ' * 310, 'start': 480, 'end': 490},
        ],
    )
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': raw}, {}, []))
    wakes = []
    monkeypatch.setattr(service, 'enqueue', lambda uid, *, at: wakes.append(at))

    assert await service.reconcile('synthetic') == 'committed'
    first, second = committed[-1][4]
    assert [first['status'], second['status']] == ['processing', 'in_progress']
    assert all(row['v3_unlocked'] and not row.get('v3_process_pending') for row in (first, second))
    assert first['structured']['title']
    assert first['_v3_preview_due_at'] == start + timedelta(seconds=3610)
    assert first['_v3_preview_due_at'] in wakes


@pytest.mark.asyncio
async def test_multiple_previews_defer_topic_lock_and_owe_no_notes(builder, monkeypatch):
    committed, messages = builder
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    start = datetime.now(timezone.utc) - timedelta(minutes=12)
    raw = source(
        started_at=start,
        finished_at=start + timedelta(seconds=30),
        transcript_segments=[
            {'text': 'first ' * 310, 'start': 0, 'end': 10},
            {'text': 'second ' * 310, 'start': 20, 'end': 30},
        ],
    )
    legacy = {
        'id': 'legacy',
        'status': 'in_progress',
        'started_at': start,
        'finished_at': start + timedelta(seconds=10),
        'v3_recording_ids': ['r'],
    }
    inputs = [{'r': raw}, {'legacy': legacy}, []]
    monkeypatch.setattr(store, 'load', lambda *a, **kw: inputs)

    def two_topics(uid, prompt):
        messages.append(prompt)
        return '{"conversations":[{"first_line":1,"title":"First","line":"One","kind":"conversation"},{"first_line":2,"title":"Second","line":"Two","kind":"conversation"}]}'

    monkeypatch.setattr(service.models, 'outline', two_topics)
    await service.reconcile('synthetic')
    first, second = committed[-1][4]
    assert first['id'] == 'legacy'
    assert first['status'] == 'processing' and second['status'] == 'in_progress'
    assert all(row['v3_unlocked'] and not row.get('v3_process_pending') for row in (first, second))
    assert all(not row['title_locked'] for row in (first, second))
    assert first['_v3_preview_due_at'] == second['_v3_preview_due_at'] == start + timedelta(seconds=3630)
    assert len(messages) == 1

    inputs[1] = {row['id']: row for row in (first, second)}
    inputs[2] = committed[-1][5]
    raw['transcript_segments'].insert(1, {'text': 'late inserted speech', 'start': 12, 'end': 14})
    await service.reconcile('synthetic')
    new_first, new_second = committed[-1][4]
    assert [row['structured']['title'] for row in (new_first, new_second)] == ['First', 'Second']
    assert len(new_first['transcript_segments']) == 2 and len(new_second['transcript_segments']) == 1
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_scoped_open_keeps_other_provisional_outlines(builder, monkeypatch):
    committed, messages = builder
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    now = datetime.now(timezone.utc)
    recordings = {}
    for rid, age in (('older', 20), ('recent', 10)):
        start = now - timedelta(minutes=age)
        recordings[rid] = source(rid, started_at=start, finished_at=start + timedelta(seconds=10))
    inputs = [recordings, {}, []]
    monkeypatch.setattr(store, 'load', lambda *a, **kw: inputs)
    await service.reconcile('synthetic')
    earlier, other = committed[-1][4]
    cache = committed[-1][5]
    assert len(cache) == len(messages) == 2

    inputs[0] = {'older': recordings['older']}
    inputs[1] = {earlier['id']: earlier}
    finished = {'fingerprint': 'finished-other-stretch', 'entries': []}
    inputs[2] = [finished, *cache]
    await service.reconcile('synthetic', on_open=True, conversation_id=earlier['id'])
    assert len(messages) == 2
    assert cache[-1] in committed[-1][5]
    assert other['id'] not in {row['id'] for row in committed[-1][4]}
    assert finished in committed[-1][5]


@pytest.mark.asyncio
async def test_configured_reconcile_retains_existing_notes_after_late_speech(builder, monkeypatch):
    committed, _ = builder
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '301')
    start = datetime.now(timezone.utc) - timedelta(minutes=10)
    end = start + timedelta(seconds=30)
    original = {'id': 'first', 'text': 'first ' * 310, 'start': 0, 'end': 10}
    appended = {'id': 'late', 'text': 'late ' * 120, 'start': 15, 'end': 30}
    raw = source(started_at=start, finished_at=end, transcript_segments=[original, appended])
    prior = {
        'id': 'card',
        'status': 'completed',
        'started_at': start,
        'finished_at': end,
        'v3_derived': True,
        'v3_recording_ids': ['r'],
        'v3_rewrites': 0,
        'structured': {'title': 'Original'},
        'summary_covers_through': end,
        'transcript_segments': [original],
    }
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': raw}, {'card': prior}, []))
    assert await service.reconcile('synthetic') == 'committed'
    (row,) = committed[-1][4]
    assert row['id'] == 'card' and len(row['transcript_segments']) == 2
    assert row['v3_rewrites'] == 0 and not row.get('v3_process_pending')
    assert row['summary_covers_through'] == end


@pytest.mark.asyncio
@pytest.mark.parametrize('age,delay', [(60, 300), (600, 3600)])
async def test_configured_builder_wakes_at_outline_then_lock(builder, monkeypatch, age, delay):
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    end = datetime.now(timezone.utc) - timedelta(seconds=age)
    raw = source(started_at=end - timedelta(seconds=10), finished_at=end)
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': raw}, {}, []))
    wakes = []
    monkeypatch.setattr(service, 'enqueue', lambda uid, *, at: wakes.append(at))

    assert await service.reconcile('synthetic') == 'committed'
    assert wakes == [end + timedelta(seconds=delay)]


@pytest.mark.parametrize('gap,continues', [(600, True), (900, False)])
def test_pending_page_continuation_uses_configured_silence(monkeypatch, gap, continues):
    monkeypatch.setenv('CONVERSATIONS_V3_SILENCE_GAP_SECONDS', '900')
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a, **kw: False)
    monkeypatch.setattr(store, 'recording_input', lambda uid, snap: snap.to_dict() if snap.exists else None)
    prefix = '/users/synthetic/conversations/'
    rows = {}
    for index in range(32):
        start = AT + timedelta(seconds=index * 10)
        rid = str(index)
        rows[prefix + rid] = source(
            rid, started_at=start, finished_at=start + timedelta(seconds=10), v3_pending_since=start
        )
    successor = rows[prefix + '31']['finished_at'] + timedelta(seconds=gap)
    rows[prefix + 'next'] = source(
        'next', started_at=successor, finished_at=successor + timedelta(seconds=10), v3_pending_since=successor
    )

    recordings, _, _ = store.load('synthetic', firestore_client=MemoryQuery(rows))
    assert 'next' not in recordings
    assert bool(recordings['31'].get('_v3_page_continues')) is continues


@pytest.mark.asyncio
async def test_provisional_window_does_not_reopen_a_locked_card_by_clock(builder, monkeypatch):
    committed, _ = builder
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    start = datetime.now(timezone.utc) - timedelta(minutes=10)
    end = start + timedelta(seconds=10)
    raw = source(started_at=start, finished_at=end, claims=[])
    prior = {
        'id': 'locked',
        'v3_derived': True,
        'status': 'completed',
        'started_at': start,
        'finished_at': end,
        'title_locked': True,
        'structured': {'title': 'Saved title', 'emoji': '🌲'},
        'v3_recording_ids': ['r'],
    }
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': raw}, {'locked': prior}, []))
    assert await service.reconcile('synthetic') == 'committed'
    [preview] = committed[-1][4]
    assert preview['id'] != 'locked' and preview['v3_unlocked']
    assert committed[-1][3]['locked']['structured'] == {'title': 'Saved title', 'emoji': '🌲'}


def test_merge_donor_task_guard_is_scoped_and_bounded():
    rows = {
        '/users/synthetic/action_items/linked': {'conversation_id': 'donor'},
        '/users/other/action_items/unrelated': {'conversation_id': 'other'},
    }
    client = MemoryQuery(rows)
    assert store.merge_donors_have_tasks('synthetic', ['other', 'donor'], firestore_client=client)
    assert not store.merge_donors_have_tasks('synthetic', ['other'], firestore_client=client)
    assert store.merge_donors_have_tasks(
        'synthetic', [f'd{i:02}' for i in range(31)] + ['donor'], firestore_client=client
    )
    assert len(client.calls) == 4
    assert all(limit == 1 for _filters, limit, _after in client.calls)


def test_prior_purge_inventory_skips_other_modes_and_stays_owner_scoped(monkeypatch):
    monkeypatch.setattr(runs, 'PRIORS_READ_PAGE', 2)
    prefix = f'/users/u/{runs.COLLECTION}/'
    client = MemoryQuery(
        {
            prefix + 'a': {'mode': 'derive'},
            prefix + 'b': {'mode': runs.LIVE_MODE},
            prefix + 'c': {'mode': 'rederive'},
            prefix + 'd': {'mode': runs.LIVE_MODE},
            prefix + 'e': {'mode': runs.LIVE_MODE},
            f'/users/other/{runs.COLLECTION}/f': {'mode': runs.LIVE_MODE},
        }
    )
    assert runs._live_run_ids('u', firestore_client=client) == ['b', 'd', 'e']
    assert len(client.calls) == 2
    assert all(filters == (('mode', '==', runs.LIVE_MODE),) and cap == 2 for filters, cap, _ in client.calls)
    client.calls.clear()
    assert runs.purge_conversation_priors('no-history', ['c0'], 'deleted', firestore_client=client) == 0
    assert len(client.calls) == 1


def test_builder_followup_distinguishes_deferred_preview_from_new_work(monkeypatch):
    prefix = '/users/synthetic/conversations/'
    rows = {prefix + 'preview': {'v3_pending': True}}
    client = MemoryQuery(rows)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)

    assert not service.has_pending('synthetic', {'preview'})
    rows[prefix + 'incoming'] = {'v3_pending': True}
    assert service.has_pending('synthetic', {'preview'})
    assert all(limit == 2 for _filters, limit, _after in client.calls)


def test_indexed_preview_with_unreadable_transcript_keeps_its_custody(monkeypatch):
    prefix = '/users/synthetic/'
    rows = {
        prefix + 'conversation_v3_leases/builder': {'unlocked_ids': ['preview']},
        prefix + 'conversations/preview': {'v3_unlocked': True, 'status': 'processing'},
    }
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a, **kw: False)

    def decode(*args):
        raise store.TranscriptBlobAbsent('synthetic unavailable blob')

    monkeypatch.setattr(store, 'decode_row', decode)
    with pytest.raises(store.Conflict, match='recording_decode_unavailable'):
        store.load('synthetic', firestore_client=MemoryQuery(rows))


def test_indexed_preview_with_unreadable_source_keeps_its_wake(monkeypatch):
    prefix = '/users/synthetic/'
    rows = {
        prefix + 'conversation_v3_leases/builder': {'unlocked_ids': ['preview']},
        prefix
        + 'conversations/preview': {
            'id': 'preview',
            'v3_unlocked': True,
            'status': 'processing',
            'v3_recording_ids': ['r'],
        },
        prefix + 'conversations/r': source(v3_pending=True, v3_pending_since=AT),
    }
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a, **kw: False)

    def decode(uid, snapshot):
        if snapshot.id == 'r':
            raise store.TranscriptBlobAbsent('synthetic unavailable source')
        return snapshot.to_dict() if snapshot.exists else None

    monkeypatch.setattr(store, 'decode_row', decode)
    with pytest.raises(store.Conflict, match='recording_decode_unavailable'):
        store.load('synthetic', firestore_client=MemoryQuery(rows))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'terminal', [{'deleted': True}, {'sync_merged_into': 'successor'}, {'data_protection_level': 'private'}]
)
async def test_builder_settles_preview_without_eligible_sources(builder, monkeypatch, terminal):
    committed, messages = builder
    start, end = AT, AT + timedelta(seconds=10)
    raw = source(claims=[{'conversation_id': 'preview', 'start': start, 'end': end}], **terminal)
    preview = {
        'id': 'preview',
        'status': 'in_progress',
        'v3_unlocked': True,
        'started_at': start,
        'finished_at': end,
        'v3_recording_ids': ['r'],
    }
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': raw}, {'preview': preview}, []))

    assert await service.reconcile('synthetic') == 'committed'
    (retired,) = committed[-1][4]
    assert retired['id'] == 'preview' and retired['status'] == 'completed'
    assert retired['home_hidden'] and not retired['v3_unlocked'] and not retired['v3_process_pending']
    assert retired['_v3_claims'] == {'r': [{'start': start, 'end': end}]}
    assert not messages
