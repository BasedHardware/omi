"""Count nested Firestore results through real memory compatibility readers."""

import time

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from database import mcp_conversation_pages, conversations
from utils.memory.memory_service import MemoryService
from utils.memory import read_resilience
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
        self.field = None

    def document(self, doc_id):
        return Ref(self.store, self.path + '/' + doc_id)

    def where(self, *args, **kwargs):
        return self

    def select(self, fields):
        return self

    def order_by(self, field, **kwargs):
        if self.field is None:
            self.field = field
        return self

    def limit(self, n):
        self.n = n
        return self

    def offset(self, n):
        self.skip = n
        return self

    def stream(self, **kwargs):
        self.store.streams += 1
        rows = [(path, data) for path, data in self.store.rows.items() if path.rsplit('/', 1)[0] == self.path]
        if self.field:
            rows.sort(key=lambda row: row[1][self.field], reverse=True)
        selected = rows[self.skip : self.skip + self.n]
        self.store.physical += min(self.skip, len(rows)) + len(selected)
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
    monkeypatch.setattr(handlers, 'MemoryService', lambda **kwargs: service)
    bounded = budget(1500)
    result = handlers.memories_page_core(
        'owner', limit=25, sort='created_desc', max_scan=5000, cursor_kind='test', budget=bounded
    )
    assert bounded.truncated and result['scan_truncated'] and result['has_more']
    assert store.batch_gets > 0 and store.streams == 2
    assert store.physical == bounded.docs_scanned
    # Existing materialized RPC accounting may overshoot by one bounded window.
    assert store.physical <= 1500 + 600
    assert result['scanned_count'] < 600
    # The full, old path traverses all rows and preserves legacy ordering.
    store.physical = store.streams = store.batch_gets = 0
    unbounded = handlers.memories_page_core('owner', limit=25, sort='created_desc', max_scan=5000, cursor_kind='test')
    assert not unbounded['scan_truncated']
    assert [row['id'] for row in unbounded['memories']] == [f'h-{i}' for i in range(25)]
    assert store.physical > 10000
    prior_reads = store.physical
    store.physical = store.streams = store.batch_gets = 0
    clean = budget(25000)
    same = handlers.memories_page_core(
        'owner', limit=25, sort='created_desc', max_scan=5000, cursor_kind='test', budget=clean
    )
    assert same['memories'] == unbounded['memories']
    assert not same['scan_truncated'] and not clean.truncated
    assert store.physical == clean.docs_scanned == 3000
    assert store.physical < prior_reads
    print(f'nested MCP exhausted={bounded.docs_scanned}; clean={clean.docs_scanned}; prior-path={prior_reads}')


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
