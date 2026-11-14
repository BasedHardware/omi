"""Reference-index privacy contracts, using the real purge and SDK filters."""

import copy
import hashlib
import hmac
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import memory_privacy_reference_index as index
from database.memory_vector_repair_outbox import write_vector_repair_purge_outbox_records
from testing.import_isolation import load_module_fresh, stub_modules


@pytest.fixture
def ledger():
    client = ModuleType('database._client')
    client.db = MagicMock()
    client.data_plane_db = client.db
    client.get_firestore_client = lambda: client.db
    client.get_data_plane_firestore_client = lambda: client.db
    holds = ModuleType('database.legal_holds')
    holds.LegalHoldAuthorityUnavailable = RuntimeError
    for name in (
        'assert_no_destructive_operation_transaction',
        'assert_destructive_gate_still_ours',
        'assert_destructive_operation_transaction',
        'current_destructive_operation_token',
    ):
        setattr(holds, name, MagicMock())
    with stub_modules({'database._client': client, 'database.legal_holds': holds}):
        yield load_module_fresh(
            'database.memory_ledger', Path(__file__).resolve().parents[2] / 'database/memory_ledger.py'
        )


class HistoryDb:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)
        self.reads = []
        self.actions = []

    def collection(self, path):
        return HistoryQuery(self, path)


class HistoryQuery:
    def __init__(self, db, path, *, tokens=None, after=None, count=None):
        self.db, self.path, self.tokens, self.after, self.count = db, path, tokens, after, count

    def document(self, uid):
        return SimpleNamespace(collection=lambda name: HistoryQuery(self.db, f'{self.path}/{uid}/{name}'))

    def where(self, *, filter):
        assert filter.field_path == index.PRIVACY_REFERENCE_TOKENS
        assert filter.op_string == 'array_contains_any'
        assert 0 < len(filter.value) <= 30
        return HistoryQuery(self.db, self.path, tokens=filter.value)

    def order_by(self, field):
        assert field == '__name__'
        return self

    def start_after(self, cursor):
        return HistoryQuery(self.db, self.path, tokens=self.tokens, after=cursor.id)

    def limit(self, count):
        return HistoryQuery(self.db, self.path, tokens=self.tokens, after=self.after, count=count)

    def stream(self):
        assert self.count is not None
        matches = []
        for path, payload in sorted(self.db.rows.items()):
            prefix = f'{self.path}/'
            if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                continue
            doc_id = path[len(prefix) :]
            if self.after is not None and doc_id <= self.after:
                continue
            if self.tokens is not None and not set(self.tokens).intersection(
                payload.get(index.PRIVACY_REFERENCE_TOKENS, [])
            ):
                continue
            matches.append((path, doc_id, payload))
        page = matches[: self.count]
        self.db.reads.append((self.path, self.tokens, self.after, [doc_id for _, doc_id, _ in page]))
        return [self.snapshot(path, doc_id, payload) for path, doc_id, payload in page]

    def snapshot(self, path, doc_id, payload):
        def delete():
            self.db.actions.append(('delete', path))
            del self.db.rows[path]

        def update(values):
            self.db.actions.append(('update', path))
            self.db.rows[path].update(values)

        return SimpleNamespace(
            id=doc_id,
            to_dict=lambda: copy.deepcopy(payload),
            reference=SimpleNamespace(delete=delete, update=update),
        )


def fixture_rows(*, indexed=True):
    rows = {}
    for collection in index.PRIVACY_HISTORY_COLLECTIONS:
        for owner in ('owner', 'other'):
            for n in range(7):
                payload = {'nested': [{'arbitrary': f'mem-{n}'}, ('also-a-leaf',)], 'unmatched-key': 'peer'}
                if collection == 'jit_proactivity_daily_budgets':
                    payload = {'planned_by_trigger': {f'mem-{n}': 1, 'keep': 2}, 'other': 'peer'}
                rows[f'users/{owner}/{collection}/row-{n}'] = payload
            rows[f'users/{owner}/{collection}/unrelated'] = {'mem-1': 'peer'}
    # These rows match only by deleted operation ID, never by memory ID.
    for collection in ('memory_commits', 'memory_outbox'):
        rows[f'users/owner/{collection}/cascade'] = {'operation_id': 'row-1', 'opaque': 'keep'}
    if indexed:
        rows = {
            path: index.with_privacy_reference_tokens(
                path.split('/')[1], payload, budget=path.split('/')[2] == 'jit_proactivity_daily_budgets'
            )
            for path, payload in rows.items()
        }
    return rows


def logical_rows(rows):
    return {path: index.privacy_history_payload(payload) for path, payload in rows.items()}


def test_tokens_cover_exact_string_leaves_and_budget_keys(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', 's' * 32)
    payload = {'map-key': ['target', ('nested', 1, None, True)], 'planned_by_trigger': {'budget-key': 2}}
    result = index.with_privacy_reference_tokens('owner', payload)
    assert index.privacy_history_payload(result) == payload
    assert result[index.PRIVACY_REFERENCE_TOKENS] == index.privacy_reference_tokens('owner', {'target', 'nested'})
    budget = index.with_privacy_reference_tokens('owner', result, budget=True)
    assert budget[index.PRIVACY_REFERENCE_TOKENS] == index.privacy_reference_tokens(
        'owner', {'target', 'nested', 'budget-key'}
    )
    assert index.with_privacy_reference_tokens('owner', budget, budget=True) == budget
    assert index.privacy_reference_tokens('other', {'target'}) != index.privacy_reference_tokens('owner', {'target'})
    expected = hmac.new(
        b's' * 32,
        json.dumps(['memory-privacy-reference.v1', 'owner', 'target'], separators=(',', ':')).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert index.privacy_reference_tokens('owner', {'target'}) == [expected]
    assert index.privacy_reference_tokens('a', {'b\nc'}) != index.privacy_reference_tokens('a\nb', {'c'})


@pytest.mark.parametrize('switch', [None, 'off', 'false', 'unexpected'])
def test_off_is_original_full_scan_even_for_unindexed_history(ledger, monkeypatch, switch):
    if switch is None:
        monkeypatch.delenv('MEMORY_PRIVACY_REFERENCE_INDEX', raising=False)
    else:
        monkeypatch.setenv('MEMORY_PRIVACY_REFERENCE_INDEX', switch)
    monkeypatch.setattr(ledger, 'MEMORY_COMMIT_PRIVACY_PURGE_PAGE_SIZE', 2)
    monkeypatch.setattr(ledger, 'privacy_reference_tokens', lambda *_: pytest.fail('off path built target tokens'))
    db = HistoryDb(fixture_rows(indexed=False))
    removed = ledger.purge_canonical_privacy_history_for_memories('owner', ['mem-1'], firestore_client=db)
    assert removed == {
        collection: (['cascade', 'row-1'] if collection in ('memory_commits', 'memory_outbox') else ['row-1'])
        for collection in index.PRIVACY_HISTORY_COLLECTIONS
        if collection != 'jit_proactivity_daily_budgets'
    }
    assert len({path for path, _, _, _ in db.reads}) == 8
    assert all(tokens is None for _, tokens, _, _ in db.reads)
    assert any(after is not None for _, _, after, _ in db.reads)
    assert db.rows['users/owner/jit_proactivity_daily_budgets/row-1']['planned_by_trigger'] == {'keep': 2}
    assert all(path in db.rows for path in fixture_rows() if path.startswith('users/other/'))


@pytest.mark.parametrize('preserve_receipts', [False, True])
def test_indexed_purge_equals_full_scan_and_retains_payload_check(ledger, monkeypatch, preserve_receipts):
    monkeypatch.setattr(ledger, 'MEMORY_COMMIT_PRIVACY_PURGE_PAGE_SIZE', 2)
    rows = fixture_rows()
    # A stale/false-positive token must never authorize deletion.
    rows['users/owner/memory_operations/unrelated'][index.PRIVACY_REFERENCE_TOKENS] = index.privacy_reference_tokens(
        'owner', {'mem-1'}
    )
    outcomes = []
    for switch in ('off', 'on'):
        monkeypatch.setenv('MEMORY_PRIVACY_REFERENCE_INDEX', switch)
        db = HistoryDb(rows)
        gates = []
        monkeypatch.setattr(ledger, 'assert_destructive_gate_still_ours', lambda *a, **kw: gates.append((a, kw)))
        removed = ledger.purge_canonical_privacy_history_for_memories(
            'owner',
            ['mem-1', 'mem-2', 'mem-3'],
            firestore_client=db,
            preserve_source_replacement_receipts=preserve_receipts,
            revalidate_gate=True,
        )
        outcomes.append((removed, logical_rows(db.rows), db.actions, len(gates)))
        if switch == 'on':
            assert all(tokens is not None and path.startswith('users/owner/') for path, tokens, _, _ in db.reads)
            assert all('row-0' not in ids for _, _, _, ids in db.reads)
    assert outcomes[0] == outcomes[1]


def test_candidates_chunk_paginate_and_deduplicate_without_scanning_peers(ledger, monkeypatch):
    monkeypatch.setenv('MEMORY_PRIVACY_REFERENCE_INDEX', 'on')
    monkeypatch.setattr(ledger, 'MEMORY_COMMIT_PRIVACY_PURGE_PAGE_SIZE', 2)
    targets = {f'mem-{i}' for i in range(65)}
    rows = {}
    for n in range(7):
        payload = index.with_privacy_reference_tokens('owner', {'nested': sorted(targets)})
        rows[f'users/owner/memory_operations/row-{n}'] = payload
    db = HistoryDb(rows)
    query = db.collection('users').document('owner').collection('memory_operations')
    result = list(ledger._iter_privacy_history_candidates(query, 'owner', targets))
    assert [doc.id for doc in result] == [f'row-{n}' for n in range(7)]
    assert len(db.reads) == 12  # three token chunks, four bounded pages each
    assert {len(tokens) for _, tokens, _, _ in db.reads} == {30, 5}
    assert {doc.id for doc in result} == {
        doc.id
        for doc in ledger._iter_collection_documents(query)
        if ledger._value_references_memory_id(index.privacy_history_payload(doc.to_dict()), targets)
    }


def test_unavailable_key_off_preserves_writes_on_fails_before_deletion(ledger, monkeypatch):
    monkeypatch.delenv('ENCRYPTION_SECRET', raising=False)
    monkeypatch.setenv('MEMORY_PRIVACY_REFERENCE_INDEX', 'off')
    payload = {'memory_id': 'target'}
    assert index.privacy_history_payload(index.with_privacy_reference_tokens('owner', payload)) == payload
    monkeypatch.setenv('MEMORY_PRIVACY_REFERENCE_INDEX', 'on')
    db = HistoryDb({'users/owner/memory_operations/row': payload})
    with pytest.raises(RuntimeError, match='secret is unavailable'):
        ledger.purge_canonical_privacy_history_for_memories('owner', ['target'], firestore_client=db)
    assert db.actions == []


@pytest.mark.parametrize('payload_uid', [None, 'payload-owner'])
def test_vector_writer_indexes_storage_owner_without_changing_logical_records(payload_uid):
    rows = {}
    db = SimpleNamespace(document=lambda path: SimpleNamespace(set=lambda data: rows.__setitem__(path, data)))
    path = 'users/storage-owner/memory_outbox/record'
    record = {'outbox_path': path, 'memory_id': 'target'}
    if payload_uid is not None:
        record['uid'] = payload_uid
    assert write_vector_repair_purge_outbox_records(db_client=db, records=[record]) == [record]
    assert rows[path] == index.with_privacy_reference_tokens('storage-owner', record)
    assert index.PRIVACY_REFERENCE_TOKENS not in record
