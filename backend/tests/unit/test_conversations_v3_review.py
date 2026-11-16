"""Round-one regressions for bounded builder work and projected read surfaces."""

from database import conversations_v3_leases as leases

from datetime import datetime, timedelta, timezone
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from database import conversations_v3 as store
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


@pytest.mark.parametrize('backfilled', [False, True])
def test_manual_end_processes_its_own_short_window(monkeypatch, backfilled):
    from utils.conversations import process_conversation as process, lifecycle
    from types import SimpleNamespace
    from database import conversations_v3_processing as writers

    row = {
        'id': 'window',
        'v3_derived': True,
        'backfilled': backfilled,
        'manual_end': True,
        'kind': 'conversation',
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT,
        'structured': {},
        'transcript_segments': [{'text': 'speech ' * 40, 'start': 0, 'end': 10, 'is_user': False}],
    }
    called = []
    monkeypatch.setattr(writers, 'begin_processing', lambda *a, **kw: True)
    monkeypatch.setattr(writers, 'settle_processing', lambda *a, **kw: None)
    monkeypatch.setattr(lifecycle, 'complete', lambda *a: pytest.fail('manual end skipped notes'))

    def full(uid, language, conversation, **kw):
        called.append(conversation)
        kw['persistence_observer'](True)
        return SimpleNamespace(status='completed')

    monkeypatch.setattr(process, 'process_conversation', full)
    service._process('u', row, 'token')
    assert called[0].id == 'window' and called[0].manual_end
    assert len(called[0].transcript_segments[0].text.split()) == 40


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
