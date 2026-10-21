"""Task-attempt memo: actual bounded queries, read counts, budgets and mutation fences."""

import asyncio
import copy
from contextvars import copy_context
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from database import memories, memory_source_index
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted

STAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)
UID = 'memo-user'


class _Reference:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def collection(self, name):
        return _Query(self.db, self.path + (name,))

    def update(self, fields):
        if self.db.on_write:
            self.db.on_write()
        self.db.rows[self.path].update(copy.deepcopy(fields))
        self.db.writes.append(('update', self.path, copy.deepcopy(fields)))

    def delete(self):
        if self.db.on_write:
            self.db.on_write()
        self.db.rows.pop(self.path, None)
        self.db.writes.append(('delete', self.path))


class _Query:
    def __init__(self, db, path, *, orders=(), cursor=None, count=None):
        self.db = db
        self.path = path
        self.orders = orders
        self.cursor = cursor
        self.count = count

    def document(self, name):
        return _Reference(self.db, self.path + (name,))

    def _copy(self, **updates):
        return _Query(
            self.db,
            self.path,
            orders=updates.get('orders', self.orders),
            cursor=updates.get('cursor', self.cursor),
            count=updates.get('count', self.count),
        )

    def order_by(self, field, direction=None):
        return self._copy(orders=self.orders + ((field, direction),))

    def start_after(self, cursor):
        return self._copy(cursor=cursor)

    def limit(self, count):
        return self._copy(count=count)

    def stream(self, **kwargs):
        # Model Firestore's ordered-field existence, tie-break and keyset
        # semantics. Count physical documents delivered, not returned slots.
        field = self.orders[0][0]
        rows = [(path, row) for path, row in self.db.rows.items() if path[:-1] == self.path and field in row]
        rows.sort(key=lambda entry: (-entry[1][field].timestamp(), entry[0][-1]))
        if self.cursor:
            after = (-self.cursor[field].timestamp(), self.cursor['__name__'].path[-1])
            rows = [(path, row) for path, row in rows if (-row[field].timestamp(), path[-1]) > after]
        rows = rows[: self.count]
        self.db.queries.append(
            (
                self.path,
                self.orders,
                self.count,
                self.cursor and (self.cursor[field], self.cursor['__name__'].path),
                kwargs,
            )
        )
        self.db.reads += len(rows)
        snapshots = [
            SimpleNamespace(id=path[-1], to_dict=lambda row=copy.deepcopy(row): copy.deepcopy(row))
            for path, row in rows
        ]
        if self.db.on_stream:
            callback, self.db.on_stream = self.db.on_stream, None
            callback()
        return iter(snapshots)


class _Db:
    def __init__(self):
        self.rows = {}
        self.queries = []
        self.writes = []
        self.reads = 0
        self.on_write = None
        self.on_stream = None
        for uid in (UID, 'other-user'):
            for index in range(5):
                self.rows[('users', uid, 'memories', f'm{index}')] = {
                    'id': 'untrusted-stored-id',
                    'content': f'content-{index}',
                    'updated_at': STAMP - timedelta(days=index),
                    'created_at': STAMP - timedelta(days=index),
                    'evidence': [{'source_id': 'conversation'}],
                }

    def collection(self, name):
        return _Query(self, (name,))


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"historical_scan_memo":100}')
    monkeypatch.delenv('FIRESTORE_HISTORICAL_SCAN_MEMO_MAX_ENTRIES', raising=False)
    monkeypatch.delenv('FIRESTORE_HISTORICAL_SCAN_MEMO_MAX_BYTES', raising=False)
    database = _Db()
    # Source-index epoch bumps are their own document; record them apart from row writes.
    database.index_bumps = []
    monkeypatch.setattr(memory_source_index, 'bump', lambda uid, _client, _writers: database.index_bumps.append(uid))
    return database


def _scan(db, uid=UID, **kwargs):
    return memories.scan_memories_updated_at_page(uid, firestore_client=db, **kwargs)


@pytest.mark.parametrize('scanner', [memories.scan_memories_updated_at_page, memories.scan_memories_created_at_page])
def test_ten_identical_pages_reduce_fifty_document_reads_to_five(db, monkeypatch, scanner):
    outputs = []
    for enabled in (False, True):
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"historical_scan_memo":100}' if enabled else '')
        db.queries.clear()
        db.reads = 0
        with memories.historical_scan_memo_scope(UID):
            pages = [scanner(UID, limit=5, firestore_client=db) for _ in range(10)]
        assert all(page == pages[0] for page in pages)
        assert (len(db.queries), db.reads) == ((1, 5) if enabled else (10, 50))
        outputs.append(pages)
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize('limit', [0, 2, 10000])
def test_off_path_keeps_original_query_cursor_limits_and_results(db, monkeypatch, limit):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)

    # OFF must not even construct a memo or measure/copy payloads for it.
    def forbidden(*args, **kwargs):
        pytest.fail('lever off allocated a memo')

    monkeypatch.setattr(memories, '_HistoricalScanMemo', forbidden)
    cursor = (STAMP.replace(tzinfo=None), 'm0')
    with memories.historical_scan_memo_scope(UID):
        first = _scan(db, limit=limit, start_after=cursor)
        second = _scan(db, limit=limit, start_after=cursor)
    bounded = max(1, min(int(limit or 100), 500))
    assert first == second
    assert len(first[0]) == min(bounded, 4)
    assert first[2] is (4 < bounded)
    assert (
        db.queries
        == [
            (
                ('users', UID, 'memories'),
                (('updated_at', 'DESCENDING'), ('__name__', None)),
                bounded,
                (STAMP, ('users', UID, 'memories', 'm0')),
                {},
            )
        ]
        * 2
    )
    assert db.reads == 2 * min(bounded, 4)


def test_enabled_without_explicit_scope_always_reads(db):
    _scan(db)
    _scan(db)
    assert len(db.queries) == 2
    assert memories._historical_scan_memo.get() is None


def test_snapshot_isolated_from_consumer_mutations_and_document_id_authoritative(db):
    with memories.historical_scan_memo_scope(UID):
        original = _scan(db, limit=2)
        expected = copy.deepcopy(original)
        assert original[0][0]['id'] == 'm0'
        original[0][0]['evidence'][0]['source_id'] = 'changed'
        original[1].clear()
        hit = _scan(db, limit=2)
        assert hit == expected
        hit[0].clear()
        assert _scan(db, limit=2) == expected
    assert len(db.queries) == 1


def test_identity_separates_uid_order_spec_cursor_limit_and_client(db):
    with memories.historical_scan_memo_scope(UID):
        _scan(db, limit=2)
        _scan(db, limit=2)
        _scan(db, uid='other-user', limit=2)
        memories.scan_memories_created_at_page(UID, firestore_client=db, limit=2)
        _scan(db, limit=2, start_after=(STAMP, 'm0'))
        _scan(db, limit=3)
        spec = replace(memories.UNIVERSAL_HISTORICAL_UPDATED_LIST_SCAN_QUERY, identifier='separate-spec')
        memories._historical_scan_page(
            UID, order_field='updated_at', query_spec=spec, limit=2, start_after=None, firestore_client=db
        )
        other_db = _Db()
        _scan(other_db, limit=2)
        assert len(other_db.queries) == 1
    assert len(db.queries) == 6


def _budget(max_documents=100, clock=lambda: 0):
    return ListReadBudget(deadline_monotonic=10, max_documents=max_documents, clock=clock)


def test_budget_identity_separates_modes_and_hits_charge_only_physical_reads(db):
    first, second = _budget(), _budget(max_documents=10)
    with memories.historical_scan_memo_scope(UID):
        _scan(db, limit=2)
        _scan(db, limit=2, budget=first)
        _scan(db, limit=2, budget=first)
        _scan(db, limit=2, budget=second)
        _scan(db, limit=2, budget=second)
    assert len(db.queries) == 3
    assert db.reads == 6
    assert (first.docs_scanned, second.docs_scanned) == (2, 2)
    assert (first.remaining_documents, second.remaining_documents) == (98, 8)


@pytest.mark.parametrize('exhaustion', ['deadline', 'documents'])
def test_cached_page_does_not_bypass_spent_budget(db, exhaustion):
    now = [0]
    budget = _budget(clock=lambda: now[0])
    with memories.historical_scan_memo_scope(UID):
        _scan(db, budget=budget)
        if exhaustion == 'deadline':
            now[0] = 11
        else:
            budget.mark_exhausted('documents')
        with pytest.raises(ListReadBudgetExhausted, match=exhaustion):
            _scan(db, budget=budget)
    assert budget.docs_scanned == 5
    assert len(db.queries) == 1


def test_failed_budgeted_scan_is_never_cached(db):
    budget = _budget(max_documents=1)
    with memories.historical_scan_memo_scope(UID):
        for _ in range(2):
            with pytest.raises(ListReadBudgetExhausted):
                _scan(db, budget=budget)
    assert len(db.queries) == 2
    assert budget.docs_scanned == db.reads == 10


@pytest.mark.parametrize('operation', ['visibility', 'review', 'kg', 'delete'])
def test_memory_mutation_fences_before_write_and_rereads_after_commit(db, operation):
    with memories.historical_scan_memo_scope(UID):
        first = _scan(db)

        # Inspect at the actual document mutation seam, before changing rows.
        def before_commit():
            memo = memories._historical_scan_memo.get()
            assert not memo.entries
            assert _scan(db) == first
            assert not memo.entries  # no caching while a writer is active

        db.on_write = before_commit
        if operation == 'visibility':
            memories.change_memory_visibility(UID, 'm0', 'private', firestore_client=db)
        elif operation == 'review':
            memories.review_memory(UID, 'm0', False, firestore_client=db)
        elif operation == 'kg':
            memories.set_memory_kg_extracted(UID, 'm0', firestore_client=db)
        else:
            memories.delete_memory(UID, 'm0', firestore_client=db)
        next_page = _scan(db)
        assert next_page != first
        assert _scan(db) == next_page
    assert len(db.queries) == 3
    assert len(db.writes) == 1
    # Visibility and review can make a row live, so they invalidate the source
    # index before and after the write; kg flags and deletes cannot add a source.
    assert db.index_bumps == ([UID, UID] if operation in {'visibility', 'review'} else [])


def test_fence_survives_lever_toggle_off_then_on(db, monkeypatch):
    with memories.historical_scan_memo_scope(UID):
        _scan(db)
        monkeypatch.delenv('FIRESTORE_READ_LEVERS')
        memories.delete_memory(UID, 'm0', firestore_client=db)
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"historical_scan_memo":100}')
        assert 'm0' not in [row['id'] for row in _scan(db)[0]]
    assert len(db.queries) == 2


def test_mutating_other_user_keeps_current_users_page(db):
    with memories.historical_scan_memo_scope(UID):
        expected = _scan(db)
        memories.delete_memory('other-user', 'm0', firestore_client=db)
        assert _scan(db) == expected
    assert len(db.queries) == 1


def test_prewrite_inflight_scan_cannot_repopulate_after_fence(db):
    db.on_stream = lambda: memories.delete_memory(UID, 'm0', firestore_client=db)
    with memories.historical_scan_memo_scope(UID):
        assert _scan(db)[0][0]['id'] == 'm0'  # already delivered by the RPC
        assert _scan(db)[0][0]['id'] == 'm1'
        _scan(db)
    assert len(db.queries) == 2


@pytest.mark.parametrize('operation', ['create', 'save', 'legacy_single', 'legacy_batch'])
def test_transaction_writes_fence_through_commit_then_allow_fresh_reuse(db, monkeypatch, operation):
    # Use the repository's read-before-write enforcing fixture for transaction
    # operations, sharing only its row store with the bounded-query fake.
    strict = StrictFirestore(db.rows)
    db.rows = strict.rows
    transaction = strict.transaction()
    monkeypatch.setenv('DREAM_AGENT_MODE', 'off')
    payloads = [
        {
            'id': f'm{index}',
            'content': f'replaced-{index}',
            'created_at': STAMP,
            'updated_at': STAMP,
            'data_protection_level': 'standard',
            'evidence': [],
        }
        for index in range(2)
    ]
    refs_and_data = [
        (strict.collection('users').document(UID).collection('memories').document(row['id']), row) for row in payloads
    ]
    commits = []

    def commit():
        memo = memories._historical_scan_memo.get()
        assert memo.writers == 1
        assert not memo.entries
        _scan(db)
        assert not memo.entries  # even commit-time reads must not be retained
        commits.append(True)

    monkeypatch.setattr(transaction, '_commit', commit)

    def append_with_builder(uid, parent, builder, **kwargs):
        assert uid == UID

        @memories.transactional
        def append(tx):
            built = builder(tx)
            built['projection_writer'](tx)

        append(transaction)
        return {'commit_id': 'test-commit'}

    monkeypatch.setattr(memories.memory_ledger, 'append_commit_with_builder', append_with_builder)
    with memories.historical_scan_memo_scope(UID):
        before = _scan(db)
        if operation == 'create':
            memories.create_memory(UID, payloads[0], firestore_client=strict)
        elif operation == 'save':
            memories.save_memories(UID, payloads, firestore_client=strict)
        elif operation == 'legacy_single':
            memories._set_memory_transaction(transaction, UID, *refs_and_data[0])
        else:
            memories._set_memories_transaction(transaction, UID, refs_and_data)
        after = _scan(db)
        assert after != before
        assert after[0][0]['content'] == 'replaced-0'
        assert _scan(db) == after
        assert memories._historical_scan_memo.get().writers == 0
    assert commits == [True]
    assert len(db.queries) == 3
    assert len(transaction.sets) == (2 if operation in ('save', 'legacy_batch') else 1)


def test_ambiguous_write_error_discards_memo(db):
    def fail():
        raise RuntimeError('commit failed')

    with memories.historical_scan_memo_scope(UID):
        expected = _scan(db)
        db.on_write = fail
        with pytest.raises(RuntimeError, match='commit failed'):
            memories.delete_memory(UID, 'm0', firestore_client=db)
        assert _scan(db) == expected
    assert len(db.queries) == 2


def test_child_task_write_invalidates_owners_page(db):
    async def child():
        memories.delete_memory(UID, 'm0', firestore_client=db)

    async def attempt():
        with memories.historical_scan_memo_scope(UID):
            _scan(db)
            await asyncio.create_task(child())
            assert _scan(db)[0][0]['id'] == 'm1'
            _scan(db)

    asyncio.run(attempt())
    assert len(db.queries) == 2


def test_empty_page_is_cached_without_changing_exhaustion(db):
    with memories.historical_scan_memo_scope(UID):
        for _ in range(3):
            assert _scan(db, start_after=(STAMP - timedelta(days=4), 'm4')) == ([], [], True)
    assert len(db.queries) == 1


def test_warm_scope_still_checks_per_user_lever_on_every_scan(db, monkeypatch):
    checks = []
    enabled = [True]

    def lever(name, key):
        checks.append((name, key))
        return enabled[0]

    monkeypatch.setattr(memories.firestore_read_levers, 'lever_enabled', lever)
    with memories.historical_scan_memo_scope(UID):
        first = _scan(db)
        assert _scan(db) == first
        enabled[0] = False
        assert _scan(db) == first
        assert _scan(db) == first
    assert checks == [('historical_scan_memo', UID)] * 5
    assert len(db.queries) == 3


def test_scope_exit_retry_nested_scope_and_copied_context_never_reuse_old_pages(db):
    with memories.historical_scan_memo_scope(UID):
        _scan(db)
        retained_context = copy_context()
        with memories.historical_scan_memo_scope(UID):
            _scan(db)
            _scan(db)
            memories.delete_memory(UID, 'm0', firestore_client=db)
        assert _scan(db)[0][0]['id'] == 'm1'
    retained_context.run(_scan, db)
    with pytest.raises(RuntimeError):
        with memories.historical_scan_memo_scope(UID):
            _scan(db)
            raise RuntimeError('retry')
    with memories.historical_scan_memo_scope(UID):
        _scan(db)
        _scan(db)
    assert len(db.queries) == 6
    assert memories._historical_scan_memo.get() is None


def test_async_child_task_cannot_inherit_owners_pages(db):
    async def child():
        _scan(db)
        _scan(db)

    async def attempt():
        with memories.historical_scan_memo_scope(UID):
            _scan(db)
            await asyncio.create_task(child())
            _scan(db)

    asyncio.run(attempt())
    assert len(db.queries) == 3


def test_explicit_executor_context_shares_attempt_and_closes_on_exit(db):
    async def attempt():
        with memories.historical_scan_memo_scope(UID):
            _scan(db)
            await asyncio.to_thread(_scan, db)
            await asyncio.to_thread(memories.delete_memory, UID, 'm0', firestore_client=db)
            assert (await asyncio.to_thread(_scan, db))[0][0]['id'] == 'm1'

    asyncio.run(attempt())
    assert len(db.queries) == 2


def test_entry_cap_evicts_oldest_and_does_not_reduce_page_limits(db, monkeypatch):
    monkeypatch.setenv('FIRESTORE_HISTORICAL_SCAN_MEMO_MAX_ENTRIES', '2')
    with memories.historical_scan_memo_scope(UID):
        _scan(db, limit=1)
        _scan(db, limit=2)
        _scan(db, limit=1)  # a hit does not move the FIFO entry
        _scan(db, limit=3)
        _scan(db, limit=2)
        _scan(db, limit=1)  # first entry was evicted
        assert len(memories._historical_scan_memo.get().entries) == 2
    assert [query[2] for query in db.queries] == [1, 2, 3, 1]


def test_payload_byte_cap_evicts_and_skips_oversize_pages(db, monkeypatch):
    # Measure retained representation just as the cache does; allow one page.
    size = memories._historical_scan_memo_bytes(copy.deepcopy(_scan(db, limit=1)))
    db.queries.clear()
    monkeypatch.setenv('FIRESTORE_HISTORICAL_SCAN_MEMO_MAX_BYTES', str(size))
    with memories.historical_scan_memo_scope(UID):
        _scan(db, limit=1)
        _scan(db, limit=1, start_after=(STAMP, 'm0'))
        memo = memories._historical_scan_memo.get()
        assert len(memo.entries) == 1
        assert memo.payload_bytes <= size
        _scan(db, limit=1)
        _scan(db, limit=5)
        _scan(db, limit=5)
    assert len(db.queries) == 5


@pytest.mark.parametrize(
    'setting', ['FIRESTORE_HISTORICAL_SCAN_MEMO_MAX_BYTES', 'FIRESTORE_HISTORICAL_SCAN_MEMO_MAX_ENTRIES']
)
def test_zero_cap_disables_retention(db, monkeypatch, setting):
    monkeypatch.setenv(setting, '0')
    with memories.historical_scan_memo_scope(UID):
        _scan(db)
        _scan(db)
        assert not memories._historical_scan_memo.get().entries
    assert len(db.queries) == 2


def test_invalid_caps_use_defaults(db, monkeypatch):
    monkeypatch.setenv('FIRESTORE_HISTORICAL_SCAN_MEMO_MAX_ENTRIES', 'invalid')
    monkeypatch.setenv('FIRESTORE_HISTORICAL_SCAN_MEMO_MAX_BYTES', '')
    with memories.historical_scan_memo_scope(UID):
        memo = memories._historical_scan_memo.get()
        assert memo.max_entries == 64
        assert memo.max_bytes == 8 * 1024 * 1024
