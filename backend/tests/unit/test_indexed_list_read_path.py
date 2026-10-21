"""Offline list-read economics, visibility equivalence, and deadline regressions."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from itertools import product
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import DeadlineExceeded
from google.cloud.firestore_v1 import And, Or

from database.firestore_retry import FIRESTORE_NO_RETRY
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted, budgeted_stream_list
from utils.memory import memory_service as service

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def _matches(payload, predicate):
    if isinstance(predicate, (And, Or)):
        results = [_matches(payload, child) for child in predicate.filters]
        return all(results) if isinstance(predicate, And) else any(results)
    value = payload
    for name in predicate.field_path.split('.'):
        if not isinstance(value, dict) or name not in value:
            return False
        value = value[name]
    if predicate.op_string == 'in':
        return value in predicate.value
    assert predicate.op_string == '=='
    return type(value) is type(predicate.value) and value == predicate.value


@dataclass
class Query:
    db: Any
    filters: tuple = ()
    maximum: int = 100
    after: Any = None
    fields: Any = None

    def document(self, doc_id):
        return SimpleNamespace(id=doc_id, collection=lambda name: self)

    def collection(self, name):
        return self

    def where(self, *, filter):
        return replace(self, filters=(*self.filters, filter))

    def order_by(self, field, direction=None):
        return self

    def start_after(self, cursor):
        return replace(self, after=cursor)

    def offset(self, offset):
        assert offset == 0
        return self

    def limit(self, count):
        return replace(self, maximum=count)

    def select(self, fields):
        return replace(self, fields=set(fields))

    def stream(self, **kwargs):
        if kwargs:
            assert kwargs['retry'] is FIRESTORE_NO_RETRY
        rows = [row for row in self.db.rows if all(_matches(row, f) for f in self.filters)]
        rows.sort(key=lambda row: (-row['updated_at'].timestamp(), row['memory_id']))
        if self.after:
            key = (-self.after['updated_at'].timestamp(), self.after['__name__'].id)
            rows = [row for row in rows if (-row['updated_at'].timestamp(), row['memory_id']) > key]
        for row in rows[: self.maximum]:
            self.db.reads += 1
            payload = dict(row) if self.fields is None else {k: v for k, v in row.items() if k in self.fields}
            yield SimpleNamespace(id=row['memory_id'], to_dict=lambda payload=payload: dict(payload))


class Db:
    def __init__(self, rows):
        self.rows = rows
        self.reads = 0

    def collection(self, path):
        return Query(self)


def _row(memory_id, *, processing='processed', status='active', required=False, **overrides) -> dict[str, Any]:
    return dict(
        memory_id=memory_id,
        uid='list-user',
        version=1,
        tier='short_term',
        status=status,
        processing_state=processing,
        content=memory_id,
        source_state='active',
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        captured_at=NOW - timedelta(days=40),
        updated_at=NOW,
        expires_at=NOW - timedelta(days=10),
        promotion={'required': required},
        **overrides,
    )


def _scan(db, monkeypatch, *, enabled, pending=True, archive=False, page_size=100):
    from utils.memory import canonical_memory_adapter as adapter

    monkeypatch.setattr(adapter, 'indexed_list_reads_enabled', lambda: enabled)
    cursor = None
    output = []
    while True:
        slots, exhausted = adapter.read_canonical_scan_page(
            'list-user',
            db_client=db,
            limit=page_size,
            start_after=cursor,
            include_pending_processing=pending,
            include_archive=archive,
            now=NOW,
        )
        output.extend(memory.id for memory, _ in slots if memory is not None)
        if exhausted:
            return output
        assert slots
        cursor = slots[-1][1]


@pytest.fixture
def large_account_reference(monkeypatch):
    rows = [_row(f'0-expired-{i:04d}', processing='pending') for i in range(1913)]
    rows += [_row(f'1-deleted-{i:04d}', status='tombstoned') for i in range(339)]
    rows += [_row(f'2-visible-{i:04d}') for i in range(348)]
    old = Db(rows)
    expected = _scan(old, monkeypatch, enabled=False)
    return rows, expected, old.reads


def test_large_account_reads_candidates_once_and_preserves_visible_order(monkeypatch, large_account_reference):
    rows, expected, raw_reads = large_account_reference
    indexed = Db(rows)
    actual = _scan(indexed, monkeypatch, enabled=True)
    assert actual == expected
    assert len(actual) == 348
    assert raw_reads == 2600
    assert indexed.reads == 348
    assert actual[100:200] == expected[100:200]  # legacy visible-offset slice


@pytest.mark.parametrize('pending', [False, True])
@pytest.mark.parametrize('archive', [False, True])
def test_gate_is_a_superset_of_released_policy_including_expired_processed(monkeypatch, pending, archive):
    rows = []
    for index, (status, processing, source, required, rejected, tier) in enumerate(
        product(
            ['active', 'hidden', 'tombstoned', 'superseded'],
            ['pending', 'processed', 'blocked'],
            ['active', 'missing', 'tombstoned', 'purged'],
            [False, True],
            [False, True],
            ['short_term', 'long_term', 'archive'],
        )
    ):
        row = _row(f'm-{index:04d}', status=status, processing=processing, required=required)
        row.update(source_state=source, tier=tier, ledger_commit_id='commit', ledger_sequence=1)
        if rejected:
            row['promotion']['user_review'] = False
        rows.append(row)
    # Missing required fields were already invalid, and optional missing
    # promotion must still admit processed rows (no backfill prerequisite).
    row = _row('no-promotion')
    row.pop('promotion')
    rows.append(row)
    assert _scan(Db(rows), monkeypatch, enabled=True, pending=pending, archive=archive) == _scan(
        Db(rows),
        monkeypatch,
        enabled=False,
        pending=pending,
        archive=archive,
    )


def test_budgeted_stream_keeps_downloaded_prefix_and_disables_sdk_retries():
    closed = []

    class SlowQuery:
        def stream(self, *, timeout, retry):
            assert timeout == 5
            assert retry is FIRESTORE_NO_RETRY
            try:
                yield 'first'
                yield 'second'
                raise DeadlineExceeded('slow provider')
            finally:
                closed.append(True)

    budget = ListReadBudget(deadline_monotonic=5, clock=lambda: 0)
    with pytest.raises(ListReadBudgetExhausted) as failure:
        budgeted_stream_list(SlowQuery(), budget)
    assert getattr(failure.value, 'partial_snapshots') == ['first', 'second']
    assert budget.docs_scanned == 2
    assert budget.truncated
    assert closed == [True]


def test_canonical_scan_preserves_verified_prefix_after_provider_deadline(monkeypatch):
    from utils.memory import canonical_memory_adapter as adapter

    real_stream = Query.stream

    def interrupted(self, **kwargs):
        for doc in real_stream(self, **kwargs):
            yield doc
            raise DeadlineExceeded('stopped after a valid row')

    monkeypatch.setattr(Query, 'stream', interrupted)
    monkeypatch.setattr(adapter, 'indexed_list_reads_enabled', lambda: True)
    budget = ListReadBudget(deadline_monotonic=5, clock=lambda: 0)
    slots, exhausted = adapter.read_canonical_scan_page(
        'list-user',
        db_client=Db([_row('visible')]),
        budget=budget,
        include_pending_processing=True,
    )
    assert [row.id for row, _ in slots if row is not None] == ['visible']
    assert not exhausted
    assert budget.truncated


def test_conversation_list_omits_transcript_before_decode_or_overlay_io(monkeypatch):
    from database import conversations

    row = _row('conversation')
    row.pop('processing_state')
    row.update(
        id='conversation',
        created_at=NOW,
        started_at=None,
        finished_at=None,
        status='completed',
        discarded=False,
        transcript_segments=b'not-a-valid-compressed-transcript',
        transcript_segments_compressed=True,
        has_transcript_corrections=True,
        user_title='My title',
        structured={'title': 'Generated'},
    )
    from models.conversation import Conversation
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Conversation.model_validate(row)
    db = Db([row])
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, 'indexed_list_reads_enabled', lambda: True)
    result = conversations.get_conversations_without_photos('list-user', list_fields_only=True)
    assert len(result) == 1
    assert 'transcript_segments' not in result[0]
    assert result[0]['structured']['title'] == 'My title'
    assert db.reads == 1
    assert Conversation.model_validate(result[0]).id == 'conversation'


def test_cursor_page_reads_only_page_plus_one_candidate(monkeypatch):
    from utils.memory import canonical_memory_adapter as adapter

    monkeypatch.setattr(adapter, 'indexed_list_reads_enabled', lambda: True)
    monkeypatch.setattr(service, 'indexed_list_reads_enabled', lambda: True)
    rows = [_row(f'0-hidden-{i:04d}', processing='pending') for i in range(2252)]
    rows += [_row(f'1-visible-{i:04d}') for i in range(348)]
    db = Db(rows)
    stream = getattr(service, '_CanonicalCursorStream')(
        service=service.MemoryService(db_client=db),
        uid='list-user',
        emitted=None,
        scan=None,
        exhausted=False,
        device_scope_request=None,
        include_pending_processing=True,
        include_archive=False,
        now=NOW,
        page_limit=100,
    )
    emitted = []
    for _ in range(100):
        row = stream.peek()
        assert row is not None
        emitted.append(row.id)
        stream.consume()
    assert emitted == [f'1-visible-{i:04d}' for i in range(100)]
    following = stream.peek()
    assert following is not None and following.id == '1-visible-0100'
    assert db.reads == 101


def test_legacy_offset_reads_visible_slice_without_raw_prefix_amplification(monkeypatch):
    from utils.memory import canonical_memory_adapter as adapter

    monkeypatch.setattr(adapter, 'indexed_list_reads_enabled', lambda: True)
    monkeypatch.setattr(service, 'indexed_list_reads_enabled', lambda: True)
    rows = [_row(f'0-hidden-{i:04d}', processing='pending') for i in range(2252)]
    rows += [_row(f'1-visible-{i:04d}') for i in range(348)]
    db = Db(rows)
    canonical = service.CanonicalMemoryBackend(db_client=db)
    result = canonical.read('list-user', limit=50, offset=100, include_pending_processing=True, now=NOW)
    assert [row.id for row in result] == [f'1-visible-{i:04d}' for i in range(100, 150)]
    assert db.reads == 150


def test_branch_merge_keeps_firestore_nanosecond_order(monkeypatch):
    from google.api_core.datetime_helpers import DatetimeWithNanoseconds
    from utils.memory import canonical_memory_adapter as adapter

    older = _row('a-pending', processing='pending', required=True)
    newer = _row('z-processed')
    older['updated_at'] = DatetimeWithNanoseconds(2026, 10, 17, nanosecond=100, tzinfo=timezone.utc)
    newer['updated_at'] = DatetimeWithNanoseconds(2026, 10, 17, nanosecond=200, tzinfo=timezone.utc)
    monkeypatch.setattr(adapter, 'indexed_list_reads_enabled', lambda: True)
    slots, _ = adapter.read_canonical_scan_page(
        'list-user',
        db_client=Db([older, newer]),
        include_pending_processing=True,
        now=NOW,
    )
    assert [cursor[1] for _, cursor in slots] == ['z-processed', 'a-pending']
