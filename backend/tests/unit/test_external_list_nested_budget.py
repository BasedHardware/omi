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
            boundary = self.after['__name__'].path
            index = next(i for i, row in enumerate(rows) if row[0] == boundary)
            rows = rows[index + 1 :]
        selected = rows[self.skip : self.skip + self.n]
        self.store.physical += min(self.skip, len(rows)) + len(selected)
        self.store.windows.append((self.path, self.orders, self.n, len(selected)))
        return iter(Snapshot(path, data) for path, data in selected)


def budget(documents):
    return ListReadBudget(deadline_monotonic=time.monotonic() + 100, max_documents=documents)


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
        return service.read(*args, **kwargs)

    monkeypatch.setattr(handlers, 'MemoryService', lambda **kwargs: SimpleNamespace(read=read))

    def run(allowance):
        store.physical = store.streams = store.batch_gets = 0
        store.windows.clear()
        calls.clear()
        result = handlers.memories_page_core(
            'owner', limit=20, sort='created_desc', max_scan=20, cursor_kind='test', budget=allowance
        )
        return result, store.physical

    unbounded, prior_reads = run(None)
    clean = budget(1000)
    same, clean_reads = run(clean)
    assert same['memories'] == unbounded['memories']
    assert [row['id'] for row in same['memories']] == ['canonical', *[f'h-{i}' for i in range(12, 24)]]
    assert not same['scan_truncated'] and not same['has_more'] and not clean.truncated
    assert clean_reads == clean.docs_scanned == 124
    assert len(calls) == 1
    assert store.batch_gets > 0
    historical = [window for window in store.windows if window[0].endswith('/memories')]
    assert {window[1][0][0] for window in historical} == {'updated_at', 'created_at'}
    assert any(window[2] > 20 for window in historical)  # Hidden rows expanded the RPC window.
    # updated_at excludes h-12; created_at supplies it. Neither index invents a field.
    assert any(window[1][0][0] == 'updated_at' and window[3] == 23 for window in historical)
    assert any(window[1][0][0] == 'created_at' and window[3] == 24 for window in historical)
    bounded = budget(25)
    truncated, bounded_reads = run(bounded)
    assert bounded.truncated and truncated['scan_truncated'] and truncated['has_more']
    assert bounded_reads == bounded.docs_scanned
    assert bounded_reads <= 25 + max(window[2] for window in store.windows)
    assert len(calls) == 1
    print(f'mixed nested MCP exhausted={bounded_reads}; clean={clean_reads}; prior-path={prior_reads}')


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
        for i in range(600)
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
    bounded = budget(1500)
    result = handlers.memories_page_core(
        'owner', limit=25, sort='created_desc', max_scan=5000, cursor_kind='test', budget=bounded
    )
    assert bounded.truncated and result['scan_truncated'] and result['has_more']
    assert len(calls) == 1
    assert store.batch_gets > 0 and store.streams == 2
    assert store.physical == bounded.docs_scanned
    # Existing materialized RPC accounting may overshoot by one bounded window.
    assert store.physical <= 1500 + 600
    assert result['scanned_count'] < 600
    # The full, old path traverses all rows and preserves legacy ordering.
    calls.clear()
    store.physical = store.streams = store.batch_gets = 0
    unbounded = handlers.memories_page_core('owner', limit=25, sort='created_desc', max_scan=5000, cursor_kind='test')
    assert not unbounded['scan_truncated']
    assert len(calls) > 1
    assert [row['id'] for row in unbounded['memories']] == [f'h-{i}' for i in range(25)]
    assert store.physical > 10000
    prior_reads = store.physical
    calls.clear()
    store.physical = store.streams = store.batch_gets = 0
    clean = budget(25000)
    same = handlers.memories_page_core(
        'owner', limit=25, sort='created_desc', max_scan=5000, cursor_kind='test', budget=clean
    )
    assert same['memories'] == unbounded['memories']
    assert len(calls) == 1
    assert not same['scan_truncated'] and not clean.truncated
    assert store.physical == clean.docs_scanned == 3000
    assert store.physical < prior_reads
    print(
        f'legacy performance MCP exhausted={bounded.docs_scanned}; clean={clean.docs_scanned}; prior-path={prior_reads}'
    )


@pytest.mark.parametrize('use_cursor', [False, True])
@pytest.mark.parametrize('activity_count', [0, 4, 100])
def test_scoring_compatibility_activity_prefix_preserves_page(monkeypatch, use_cursor, activity_count):
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

    def read(uid, *, limit, offset, budget=None):
        calls.append((limit, offset, budget))
        return service.read(uid, limit=limit, offset=offset, budget=budget)

    monkeypatch.setattr(handlers, 'MemoryService', lambda **kwargs: SimpleNamespace(read=read))
    position = {'offset': 1}
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
        {'cursor_token': encode_cursor(kind='test', uid='owner', position=position, filters=filters)}
        if use_cursor
        else {'offset': 1}
    )
    kwargs = dict(limit=25, sort='scoring_desc', max_scan=5000, cursor_kind='test', **pagination)
    old = handlers.memories_page_core('owner', **kwargs)
    prior_calls, prior_reads = list(calls), store.physical
    assert prior_reads == (1100 if activity_count == 100 else 500)
    calls.clear()
    store.physical = 0
    allowance = budget(1000)
    new = handlers.memories_page_core('owner', budget=allowance, **kwargs)
    assert (
        [row['id'] for row in new['memories']]
        == [row['id'] for row in old['memories']]
        == [f'm-{i}' for i in range(activity_count + 1, activity_count + 26)]
    )
    assert new['has_more'] == old['has_more'] is True
    assert not new['scan_truncated'] and not old['scan_truncated']
    assert calls == prior_calls
    assert all(call[2] is None for call in calls)
    assert store.physical == prior_reads
    assert allowance.docs_scanned == 0 and not allowance.truncated
    print(f'scoring activity={activity_count} cursor={use_cursor} prior/on physical reads={prior_reads}')


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
