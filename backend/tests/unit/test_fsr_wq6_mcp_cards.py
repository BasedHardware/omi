"""WQ6: count physical query reads, including billed offsets and empty RPCs."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from config import firestore_read_levers
from database import mcp_conversation_pages as pages
from utils.mcp_server.errors import stable_error_code, tool_error_from_http
from utils.mcp_server.handlers import conversations as handler
from utils.other.list_budget import ListReadBudget

UID = 'wq6-user'
NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)
RULE_DISCARD = {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'filler_only'}


class Snapshot:
    update_time = NOW

    def __init__(self, row):
        self.id = row['id']
        self.row = row

    def to_dict(self):
        return deepcopy(self.row)


class Ref:
    def __init__(self, doc_id):
        self.id = doc_id


class Query:
    def __init__(self, store, *, filters=(), orders=(), size=None, skip=0, after=None, fields=None):
        self.store = store
        self.filters, self.orders = filters, orders
        self.size, self.skip, self.after, self.fields = size, skip, after, fields

    def clone(self, **changes):
        values = {key: getattr(self, key) for key in ('filters', 'orders', 'size', 'skip', 'after', 'fields')}
        return Query(self.store, **(values | changes))

    def where(self, *, filter):
        return self.clone(filters=(*self.filters, filter))

    def order_by(self, field, direction=None):
        return self.clone(orders=(*self.orders, field))

    def select(self, fields):
        return self.clone(fields=fields)

    def limit(self, count):
        assert count > 0
        return self.clone(size=count)

    def offset(self, count):
        return self.clone(skip=count)

    def start_after(self, position):
        return self.clone(after=(position['created_at'], position['__name__'].id))

    def document(self, doc_id):
        return Ref(doc_id)

    def stream(self, **kwargs):
        assert self.size is not None, 'never allow an unbounded query'
        rows = list(self.store.rows)
        for f in self.filters:

            def value(row):
                for part in f.field_path.split('.'):
                    row = row.get(part, {})
                return row

            if f.op_string == '==':
                rows = [row for row in rows if value(row) == f.value]
            elif f.op_string == 'in':
                rows = [row for row in rows if value(row) in f.value]
            elif f.op_string == '>=':
                rows = [row for row in rows if value(row) >= f.value]
            elif f.op_string == '<=':
                rows = [row for row in rows if value(row) <= f.value]
            else:
                raise AssertionError(f.op_string)
        rows.sort(key=lambda row: (row['created_at'], row['id']), reverse=True)
        if self.after:
            rows = [row for row in rows if (row['created_at'], row['id']) < self.after]
        skipped = min(self.skip, len(rows))
        selected = rows[self.skip : self.skip + self.size]
        self.store.reads += max(1, skipped + len(selected))
        self.store.calls.append((self.size, self.skip, self.after, self.fields))
        return iter(Snapshot(row) for row in selected)


class Store:
    def __init__(self, rows):
        self.rows = rows
        self.reads = 0
        self.calls = []

    def collection(self, name):
        assert name in {'users', 'conversations'}
        return self if name == 'users' else Query(self)

    def document(self, uid):
        assert uid == UID
        return self


def row(n, **changes):
    return {
        'id': f'c{n:04}',
        'created_at': NOW - timedelta(minutes=n),
        'status': 'completed',
        'discarded': False,
        'structured': {'title': f'Card {n}', 'category': 'work'},
        **changes,
    }


def enable(monkeypatch, on):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"mcp_conversation_cards_cache":100}' if on else '{}')


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv('FSR_MCP_CARDS_MAX_READS', raising=False)
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)


@pytest.mark.parametrize('keyset', [False, True])
def test_read_count_and_identical_response_with_hidden_row(monkeypatch, keyset):
    rows = [row(n, **({'deleted': True} if n == 2 else {})) for n in range(40)]
    counts, responses = [], []
    for on in (False, True):
        enable(monkeypatch, on)
        store = Store(rows)
        if keyset:
            responses.append(pages.get_mcp_conversation_cards_page(UID, 10, firestore_client=store))
        else:
            responses.append(pages.get_mcp_conversation_cards(UID, 10, 1, firestore_client=store))
        counts.append(store.reads)
    assert responses[0] == responses[1]
    assert counts == ([22, 12] if keyset else [21, 12])


def test_unset_lever_preserves_legacy_windows_even_with_tiny_cap(monkeypatch):
    monkeypatch.setenv('FSR_MCP_CARDS_MAX_READS', '2')
    store = Store([row(n, **({'deleted': True} if n == 2 else {})) for n in range(40)])
    pages.get_mcp_conversation_cards(UID, 10, 1, firestore_client=store)
    assert [(size, skip) for size, skip, *_ in store.calls] == [(10, 1), (10, 0)]
    assert store.reads == 21


def test_existing_mcp_handler_offset_to_cursor_read_proof(monkeypatch):
    counts, outputs = [], []
    for on in (False, True):
        enable(monkeypatch, on)
        store = Store([row(n) for n in range(100)])
        monkeypatch.setattr(pages, 'get_firestore_client', lambda: store)
        first = handler.get_conversations(UID, {'limit': 10})
        second = handler.get_conversations(
            UID, {'limit': 10, **({'cursor': first['next_cursor']} if on else {'offset': 10})}
        )
        outputs.append(second['conversations'])
        counts.append(store.reads)
    assert outputs[0] == outputs[1]
    assert counts == [32, 22]  # Same two pages; cursor avoids ten billed skips.


@pytest.mark.parametrize('keyset', [False, True])
def test_visibility_filters_curated_rows_and_encryption_unchanged(monkeypatch, keyset):
    rows = [
        row(0, deleted=True),
        row(1, relevance_decision=RULE_DISCARD),
        row(2, dream_duplicate_of='other'),
        row(3, discarded=True),
        row(4, status='processing'),
        row(5, relevance_decision=RULE_DISCARD, starred=True),
        row(6, relevance_decision=RULE_DISCARD, folder_user_set=True),
        row(7, data_protection_level='enhanced'),
        row(8),
    ]
    # Exercise the existing decryption decorator, without external key material.
    from database import conversations

    monkeypatch.setattr(conversations, '_decrypt_conversation_data', lambda data, uid: {**data, 'decrypted': uid})
    results = []
    for on in (False, True):
        enable(monkeypatch, on)
        store = Store(rows)
        kwargs = dict(firestore_client=store, categories=['work'], start_date=NOW - timedelta(minutes=7), end_date=NOW)
        result = (
            pages.get_mcp_conversation_cards_page(UID, 3, **kwargs)[0]
            if keyset
            else pages.get_mcp_conversation_cards(UID, 3, 0, **kwargs)
        )
        results.append(result)
    assert results[0] == results[1]
    assert [r['id'] for r in results[1]] == ['c0005', 'c0006', 'c0007']
    assert results[1][-1]['decrypted'] == UID


def test_keyset_hard_cap_and_resume_across_dense_tombstones(monkeypatch):
    enable(monkeypatch, True)
    monkeypatch.setenv('FSR_MCP_CARDS_MAX_READS', '7')
    rows = [row(n, deleted=n < 15) for n in range(20)]
    store = Store(rows)
    after, found = None, []
    for _ in range(10):
        before = store.reads
        page, after = pages.get_mcp_conversation_cards_page(UID, 3, after=after, firestore_client=store)
        assert store.reads - before <= 7
        found.extend(r['id'] for r in page)
        if after is None:
            break
    assert found == [f'c{n:04}' for n in range(15, 20)]
    assert after is None


@pytest.mark.parametrize('keyset,limit,offset', [(False, 10, 100000), (False, 0, 0), (True, 1501, 0)])
def test_expensive_or_invalid_requests_rejected_before_any_read(monkeypatch, keyset, limit, offset):
    enable(monkeypatch, True)
    store = Store([row(n) for n in range(20)])
    with pytest.raises(HTTPException, match='cursor') as error:
        if keyset:
            pages.get_mcp_conversation_cards_page(UID, limit, firestore_client=store)
        else:
            pages.get_mcp_conversation_cards(UID, limit, offset, firestore_client=store)
    assert error.value.status_code == 400
    assert stable_error_code(tool_error_from_http(error.value)) == 'invalid_arguments'
    assert store.reads == 0


def test_offset_cap_counts_billed_skips_and_never_reports_false_end(monkeypatch):
    enable(monkeypatch, True)
    monkeypatch.setenv('FSR_MCP_CARDS_MAX_READS', '7')
    store = Store([row(n, deleted=True) for n in range(20)])
    with pytest.raises(HTTPException, match='cursor'):
        pages.get_mcp_conversation_cards(UID, 3, 2, firestore_client=store)
    assert store.reads == 7


def test_cursor_ties_do_not_skip_lookahead(monkeypatch):
    enable(monkeypatch, True)
    store = Store([row(n, created_at=NOW) for n in range(9)])
    after, ids = None, []
    while True:
        page, after = pages.get_mcp_conversation_cards_page(UID, 2, after=after, firestore_client=store)
        ids.extend(r['id'] for r in page)
        if after is None:
            break
    assert ids == [f'c{n:04}' for n in reversed(range(9))]


def test_no_stale_cache_after_explicit_mutations(monkeypatch):
    enable(monkeypatch, True)
    store = Store([row(1), row(2), row(3)])
    assert pages.get_mcp_conversation_cards_page(UID, 10, firestore_client=store)[0]
    store.rows[0]['deleted'] = True
    store.rows[1]['structured']['title'] = 'Updated'
    store.rows.append(row(0))
    result = pages.get_mcp_conversation_cards_page(UID, 10, firestore_client=store)[0]
    assert [r['id'] for r in result] == ['c0000', 'c0002', 'c0003']
    assert result[1]['structured']['title'] == 'Updated'


def test_registered_lever_is_default_off_and_uid_scoped(monkeypatch):
    assert 'mcp_conversation_cards_cache' in firestore_read_levers.KNOWN_LEVERS
    assert pages._bounded_read_cap(UID) is None
    monkeypatch.setattr(pages, 'lever_enabled', lambda name, uid: uid == UID)
    assert pages._bounded_read_cap(UID) == 1501
    assert pages._bounded_read_cap('other-user') is None
    monkeypatch.setenv('FSR_MCP_CARDS_MAX_READS', 'invalid')
    assert pages._bounded_read_cap(UID) == 1501


def test_existing_request_budget_still_applies(monkeypatch):
    enable(monkeypatch, True)
    store = Store([row(n) for n in range(20)])
    budget = ListReadBudget(deadline_monotonic=float('inf'), max_documents=2)
    assert pages.get_mcp_conversation_cards(UID, 3, 10, firestore_client=store, budget=budget) == []
    assert budget.truncated
    assert store.reads == 0
