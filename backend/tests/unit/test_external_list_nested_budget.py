"""Count nested Firestore results through real memory compatibility readers."""

import copy
import time

import pytest

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from database import mcp_conversation_pages, conversations
from models.product_memory import MemoryItem
from utils.memory.memory_service import MemoryService
from utils.memory import read_resilience
from utils.mcp_server.cursors import encode_cursor
from utils.mcp_server.handlers import memories as handlers
from utils.mcp_server.errors import ToolExecutionError
from utils.other.list_budget import ListReadBudget


class Snapshot:
    def __init__(self, path, data):
        self.reference = SimpleNamespace(path=path)
        self.id = path.rsplit('/', 1)[-1]
        self.exists = data is not None
        self.data = data
        self.update_time = None

    def to_dict(self):
        return self.data


class Store:
    def __init__(self, rows):
        self.rows = rows
        self.physical = 0
        self.streams = 0
        self.batch_gets = 0
        self.windows = []

    def collection(self, path):
        return Query(self, path)

    def document(self, path):
        return Ref(self, path)

    def get_all(self, refs, **kwargs):
        self.batch_gets += 1
        self.physical += len(refs)
        return [Snapshot(ref.path, self.rows.get(ref.path)) for ref in refs]


class Ref:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def collection(self, path):
        return Query(self.store, self.path + '/' + path)

    def get(self, **kwargs):
        self.store.physical += 1
        return Snapshot(self.path, self.store.rows.get(self.path))


class Query:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self.n = 100000
        self.skip = 0
        self.orders = []
        self.filters = []
        self.after = None

    def document(self, doc_id):
        return Ref(self.store, self.path + '/' + doc_id)

    def where(self, *args, **kwargs):
        query = copy.copy(self)
        field_filter = kwargs.get('filter')
        constraint = (field_filter.field_path, field_filter.op_string, field_filter.value) if field_filter else args
        query.filters = self.filters + [constraint]
        return query

    def select(self, fields):
        return self

    def order_by(self, field, direction=None):
        query = copy.copy(self)
        query.orders = self.orders + [(field, direction)]
        return query

    def limit(self, n):
        query = copy.copy(self)
        query.n = n
        return query

    def offset(self, n):
        query = copy.copy(self)
        query.skip = n
        return query

    def start_after(self, position):
        query = copy.copy(self)
        query.after = position
        return query

    def stream(self, **kwargs):
        self.store.streams += 1
        rows = [(path, data) for path, data in self.store.rows.items() if path.rsplit('/', 1)[0] == self.path]
        for field, op, value in self.filters:
            assert op in {'==', 'in', '>=', '<='}, op
            rows = [
                row
                for row in rows
                if field in row[1]
                and (
                    (op == '==' and row[1][field] == value)
                    or (op == 'in' and row[1][field] in value)
                    or (op == '>=' and row[1][field] >= value)
                    or (op == '<=' and row[1][field] <= value)
                )
            ]
        # Firestore order_by excludes documents lacking the ordered field.
        for field, direction in reversed(self.orders):
            if field != '__name__':
                rows = [row for row in rows if field in row[1]]
            rows.sort(
                key=lambda row: row[0] if field == '__name__' else row[1][field],
                reverse=direction == 'DESCENDING',
            )
        if self.after:
            boundary = self.after['__name__'].path if isinstance(self.after, dict) else self.after.reference.path
            index = next(i for i, row in enumerate(rows) if row[0] == boundary)
            rows = rows[index + 1 :]
        selected = rows[self.skip : self.skip + self.n]
        self.store.physical += min(self.skip, len(rows)) + len(selected)
        self.store.windows.append((self.path, self.orders, self.n, len(selected)))
        return iter(Snapshot(path, data) for path, data in selected)


def budget(documents):
    return ListReadBudget(deadline_monotonic=time.monotonic() + 100, max_documents=documents)


@pytest.mark.parametrize('bounds', ['start', 'end', 'both'])
def test_date_bounded_hidden_memory_windows_keep_released_prefix_queries(monkeypatch, bounds):
    from database import memories

    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    rows = {
        f'users/owner/memories/h-{i:02}': {
            'id': f'h-{i:02}',
            'category': 'work',
            'created_at': now - timedelta(seconds=i),
            **({'updated_at': now - timedelta(seconds=i)} if i != 12 else {}),
            **({'user_review': False} if i < 12 else {}),
        }
        for i in range(24)
    }
    kwargs = {}
    if bounds in {'start', 'both'}:
        kwargs['start_date'] = now - timedelta(days=1)
    if bounds in {'end', 'both'}:
        kwargs['end_date'] = now + timedelta(days=1)

    def no_cursor(*args):
        raise AssertionError('Date-bounded queries must retain their released prefix shape')

    monkeypatch.setattr(Query, 'start_after', no_cursor)
    baseline = Store(rows)
    monkeypatch.setenv('OMI_MEMORY_INCREMENTAL_INDEX_WINDOWS_ENABLED', 'false')
    expected = memories.list_memory_updated_or_created_index('owner', limit=4, firestore_client=baseline, **kwargs)
    current = Store(rows)
    monkeypatch.delenv('OMI_MEMORY_INCREMENTAL_INDEX_WINDOWS_ENABLED')
    actual = memories.list_memory_updated_or_created_index('owner', limit=4, firestore_client=current, **kwargs)
    assert actual == expected
    assert [row['id'] for row in actual] == [f'h-{i:02}' for i in range(12, 16)]
    assert current.windows == baseline.windows and len(current.windows) > 2


def test_mcp_created_desc_bounds_actual_dual_windows_status_and_hydration(monkeypatch):
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    rows = {
        f'users/owner/memories/h-{i}': {
            'id': f'h-{i}',
            'content': f'Legacy durable fact {i}',
            'category': 'work',
            'created_at': now - timedelta(seconds=i),
            'updated_at': now - timedelta(seconds=i),
            'data_protection_level': 'standard',
            'reviewed': False,
            **({'user_review': False} if i < 12 else {}),
        }
        for i in range(24)
    }
    # This row can only enter through the created_at index, as in Firestore.
    del rows['users/owner/memories/h-12']['updated_at']
    canonical = MemoryItem(
        memory_id='canonical',
        ledger_commit_id='test-commit',
        ledger_sequence=1,
        uid='owner',
        version=1,
        tier='long_term',
        status='active',
        processing_state='processed',
        source_state='active',
        content='Canonical durable fact',
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        captured_at=now + timedelta(seconds=1),
        updated_at=now + timedelta(seconds=1),
    )
    rows['users/owner/memory_items/canonical'] = canonical.model_dump(mode='python')
    # Advance admission time between synthetic requests, rather than exhausting
    # the process-wide burst allowance by running the old prefix loop instantly.
    ticks = iter(range(1000))
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance(clock=lambda: next(ticks)))
    store = Store(rows)
    service = MemoryService(db_client=store)
    calls = []

    def read(*args, **kwargs):
        calls.append(kwargs)
        return service.read_mcp_filtered(*args, **kwargs)

    monkeypatch.setattr(handlers, 'MemoryService', lambda **kwargs: SimpleNamespace(read_mcp_filtered=read))

    def run(allowance):
        store.physical = store.streams = store.batch_gets = 0
        store.windows.clear()
        calls.clear()
        return handlers.memories_page_core(
            'owner',
            limit=20,
            sort='created_desc',
            reviewed=False,
            max_scan=100,
            cursor_kind='test',
            budget=allowance,
        )

    unbounded = run(None)
    clean = budget(1000)
    same = run(clean)
    assert same['memories'] == unbounded['memories']
    assert [row['id'] for row in same['memories']] == ['canonical', *[f'h-{i}' for i in range(12, 24)]]
    assert not same['scan_truncated'] and not same['has_more'] and not clean.truncated
    assert store.physical == clean.docs_scanned
    assert len(calls) == 1 and store.batch_gets > 0
    historical = [window for window in store.windows if window[0].endswith('/memories')]
    assert len(historical) == 2
    assert {window[1][0][0] for window in historical} == {'updated_at', 'created_at'}
    assert sum(window[3] for window in historical if window[1][0][0] == 'updated_at') == 23
    assert sum(window[3] for window in historical if window[1][0][0] == 'created_at') == 24
    exhausted = budget(25)
    with pytest.raises(ToolExecutionError, match='budget exhausted'):
        run(exhausted)
    assert exhausted.truncated
    # A cap below the complete candidate set cannot be mistaken for exhaustion.
    with pytest.raises(ToolExecutionError, match='20 candidates'):
        handlers.memories_page_core(
            'owner',
            limit=20,
            sort='created_desc',
            reviewed=False,
            max_scan=20,
            cursor_kind='test',
        )


def test_mcp_created_desc_single_window_reduces_legacy_physical_reads(monkeypatch):
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    rows = {
        f'users/owner/memories/h-{i}': {
            'id': f'h-{i}',
            'content': f'Legacy durable fact {i}',
            'category': 'work',
            'created_at': now - timedelta(seconds=i),
            'updated_at': now - timedelta(seconds=i),
            'data_protection_level': 'standard',
            'reviewed': False,
        }
        for i in range(6854)
    }
    # Advance admission time between synthetic requests; offline queries run
    # faster than the process-wide eight-operation burst would allow in a loop.
    ticks = iter(range(1000))
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance(clock=lambda: next(ticks)))
    store = Store(rows)
    service = MemoryService(db_client=store)
    # Empty canonical stream, with real mixed merge, dual history-index reads,
    # canonical/override status batches and hydration. No network or cloud clients.
    monkeypatch.setattr(service._canonical, 'read', lambda *a, **k: [])
    calls = []

    def read(*args, **kwargs):
        calls.append(kwargs)
        return service.read(*args, **kwargs)

    monkeypatch.setattr(handlers, 'MemoryService', lambda **kwargs: SimpleNamespace(read=read))
    # Main's unbudgeted global collector reads a 100-row prefix, then 200.
    service.read('owner', limit=100, offset=0)
    service.read('owner', limit=100, offset=100)
    main_reads = store.physical
    store.physical = store.streams = store.batch_gets = 0
    unbounded = handlers.memories_page_core('owner', limit=25, sort='created_desc', cursor_kind='test')
    assert [row['id'] for row in unbounded['memories']] == [f'h-{i}' for i in range(25)]
    unbounded_reads = store.physical
    calls.clear()
    store.physical = store.streams = store.batch_gets = 0
    clean = budget(25000)
    same = handlers.memories_page_core('owner', limit=25, sort='created_desc', cursor_kind='test', budget=clean)
    assert same['memories'] == unbounded['memories']
    assert len(calls) == 1 and not clean.truncated and same['scan_truncated']
    assert store.physical == clean.docs_scanned == unbounded_reads
    assert store.physical <= main_reads
    assert calls[0]["limit"] == 100
    assert same["source_window_limit"] == 100 and "bounded" in same["coverage"]


@pytest.mark.parametrize('use_cursor', [False, True])
@pytest.mark.parametrize('activity_count', [0, 4, 100])
def test_scoring_compatibility_activity_prefix_preserves_page(monkeypatch, use_cursor, activity_count):
    monkeypatch.setenv('MEMORY_V3_CURSOR_SECRET', 'synthetic-mcp-list-test-secret')
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    rows = {
        f'users/owner/memories/m-{i}': {
            'id': f'm-{i}',
            'content': 'Focused on email' if i < activity_count else f'Durable fact {i}',
            'category': 'work',
            'created_at': now - timedelta(seconds=i),
            'updated_at': now - timedelta(seconds=i),
            'data_protection_level': 'standard',
            'reviewed': False,
        }
        for i in range(140)
    }
    store = Store(rows)
    service = MemoryService(db_client=store)
    monkeypatch.setattr(service._canonical, 'read', lambda *a, **k: [])
    ticks = iter(range(1000))
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance(clock=lambda: next(ticks)))
    calls = []

    def read(uid, **kwargs):
        calls.append(kwargs)
        return service.read_page(uid, **kwargs)

    monkeypatch.setattr(handlers, 'MemoryService', lambda **kwargs: SimpleNamespace(read_page=read))
    filters = {
        'categories': [],
        'sort': 'scoring_desc',
        'reviewed': None,
        'manually_added': None,
        'updated_after': None,
        'include_activity': False,
        'include_sensitive': True,
    }
    pagination = (
        {'cursor_token': encode_cursor(kind='test', uid='owner', position={'offset': 1}, filters=filters)}
        if use_cursor
        else {'offset': 1}
    )
    kwargs = dict(limit=25, sort='scoring_desc', max_scan=5000, cursor_kind='test', **pagination)
    old = handlers.memories_page_core('owner', **kwargs)
    calls.clear()
    store.physical = 0
    allowance = budget(10000)
    if activity_count == 100:
        # The shared resilience allowance admits two backing-store operations.
        # A sparse compatibility page needing more must fail explicitly rather
        # than reset that allowance or return a misleading empty success.
        with pytest.raises(ToolExecutionError, match='Memory read admission exhausted') as exc:
            handlers.memories_page_core('owner', budget=allowance, **kwargs)
        assert exc.value.http_status == 503
        assert len(calls) == 3 and store.physical < 5000
        assert all(call.get('request_budget') is allowance for call in calls)
        return
    new = handlers.memories_page_core('owner', budget=allowance, **kwargs)
    ids = [row['id'] for row in new['memories']]
    assert ids == [row['id'] for row in old['memories']]
    assert ids == [f'm-{i}' for i in range(activity_count + 1, activity_count + 1 + len(ids))]
    assert new['has_more'] and old['has_more']
    assert not allowance.truncated and len(calls) <= 4
    assert all(call['limit'] <= 26 for call in calls)
    assert all(call.get('request_budget') is allowance for call in calls)
    assert store.physical < 5000
    if len(ids) < 25:
        assert new['scan_truncated'] and old['scan_truncated']
    else:
        assert not new['scan_truncated'] and not old['scan_truncated']


def test_card_offsets_stop_before_rpc_and_small_pages_charge_skips():
    store = Store(
        {
            f'users/owner/conversations/c-{i}': {
                'id': f'c-{i}',
                'created_at': datetime(2026, 10, 18, tzinfo=timezone.utc),
                'discarded': False,
                'status': 'completed',
                'data_protection_level': 'standard',
            }
            for i in range(100)
        }
    )
    too_large = budget(50)
    result = mcp_conversation_pages.get_mcp_conversation_cards(
        'owner', 10, 10000, firestore_client=store, budget=too_large
    )
    assert result == [] and too_large.truncated and store.physical == store.streams == 0
    allowed = budget(50)
    result = mcp_conversation_pages.get_mcp_conversation_cards('owner', 10, 20, firestore_client=store, budget=allowed)
    assert len(result) == 10
    assert store.physical == allowed.docs_scanned == 30


def test_legacy_transcript_folder_starred_reader_bounds_offsets(monkeypatch):
    store = Store({})
    monkeypatch.setattr(conversations, 'db', store)
    for extra in ({}, {'folder_id': 'folder'}, {'starred': True}):
        allowance = budget(50)
        assert (
            conversations.get_conversations_without_photos(
                'owner', 10, 10000, statuses=['completed'], budget=allowance, **extra
            )
            == []
        )
        assert allowance.truncated
    assert store.streams == store.physical == 0
