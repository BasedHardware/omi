"""Request-scoped list-read budget contract for the three prod 504 routes.

GET /v1/action-items, GET /v1/conversations, and GET /v3/memories must not
consume the whole ``HTTP_GET_TIMEOUT`` (30s) budget and surface as a bare
middleware 504 (#11831). The contract under test:

* a request-scoped ``ListReadBudget`` owns the monotonic deadline, the
  document allowance, aggregate counters, and a typed exhaustion outcome;
* wall-clock interrupts the *blocking* Firestore RPC (per-RPC timeouts
  derived from the remaining internal deadline), not just loop checks;
* actual aggregate work is charged — conversations ``offset()`` rows before
  the query, action-items active+legacy+completed under one budget, memories
  dual-window scans plus emitted and suppressed rows;
* exhaustion maps to the explicit truncated surface (``X-Omi-List-Truncated``
  header, action-items ``truncated``/``has_more``) with no resumable cursor,
  while non-budget errors keep their existing statuses.
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from google.api_core.exceptions import DeadlineExceeded as FirestoreDeadlineExceeded
from google.api_core.exceptions import NotFound as FirestoreNotFound

import pytest

from routers import memories as mem_mod
import routers.action_items as action_items_router
import routers.conversations as conversations_router

from utils.other.list_budget import (
    OMI_LIST_TRUNCATED_HEADER,
    OMI_LIST_TRUNCATED_VALUE,
    LIST_READ_DEFAULT_BUDGET_SECONDS,
    ListReadBudget,
    ListReadBudgetExhausted,
    budgeted_get_all,
    budgeted_stream_iter,
    budgeted_stream_list,
    list_read_budget_for_request,
    resolve_list_read_budget_seconds,
)


class FakeClock:
    def __init__(self, start: float = 1_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _budget(clock: FakeClock, *, seconds: float = 24.0, max_documents: int = 25_000) -> ListReadBudget:
    return ListReadBudget(
        deadline_monotonic=clock.now + seconds,
        max_documents=max_documents,
        route='test',
        clock=clock,
        started_monotonic=clock.now - 0.0,
    )


# ---------------------------------------------------------------------------
# A. Budget module unit tests
# ---------------------------------------------------------------------------


def test_rpc_timeout_derives_from_remaining_deadline():
    clock = FakeClock()
    budget = _budget(clock, seconds=24.0)
    assert budget.rpc_timeout() == pytest.approx(24.0)
    clock.advance(10.0)
    assert budget.rpc_timeout() == pytest.approx(14.0)


def test_rpc_timeout_refuses_calls_that_cannot_finish():
    clock = FakeClock()
    budget = _budget(clock, seconds=0.01)
    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        budget.rpc_timeout()
    assert excinfo.value.reason == 'deadline'
    assert budget.truncated


def test_document_allowance_exhaustion_is_typed_and_off_by_one_safe():
    clock = FakeClock()
    budget = _budget(clock, max_documents=3)
    budget.charge(3)
    assert not budget.truncated
    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        budget.charge(1)
    assert excinfo.value.reason == 'documents'
    assert budget.truncated
    assert budget.exhaustion_reason == 'documents'
    assert budget.docs_scanned == 4


def test_deadline_check_raises_typed():
    clock = FakeClock()
    budget = _budget(clock, seconds=5.0)
    clock.advance(5.0)
    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        budget.check()
    assert excinfo.value.reason == 'deadline'


def test_first_exhaustion_reason_wins():
    clock = FakeClock()
    budget = _budget(clock, seconds=1.0, max_documents=1)
    budget.charge(1)  # documents has 0 remaining but not negative yet
    clock.advance(10.0)
    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        budget.charge(1)
    # Whichever fires first sticks; a later reason cannot rewrite it.
    assert excinfo.value.reason == budget.exhaustion_reason


def test_for_request_honors_middleware_start_stamp():
    clock = FakeClock()
    request = SimpleNamespace(state=SimpleNamespace(omi_request_started_monotonic=clock.now - 6.0))
    budget = list_read_budget_for_request(request, route='x', seconds=24.0, clock=clock)
    # Six seconds already elapsed before the handler ran count against the
    # internal deadline — the budget may not restart the clock mid-request.
    assert budget.rpc_timeout() == pytest.approx(18.0)


def test_for_request_without_stamp_starts_now():
    clock = FakeClock()
    budget = list_read_budget_for_request(None, route='x', seconds=24.0, clock=clock)
    assert budget.rpc_timeout() == pytest.approx(24.0)


def test_budget_derivation_leaves_headroom_under_the_edge_cutoff(monkeypatch):
    monkeypatch.delenv('OMI_LIST_READ_BUDGET_SECONDS', raising=False)
    monkeypatch.setenv('HTTP_GET_TIMEOUT', '30')
    assert resolve_list_read_budget_seconds() == pytest.approx(24.0)
    monkeypatch.setenv('HTTP_GET_TIMEOUT', '9')
    assert resolve_list_read_budget_seconds() == pytest.approx(3.0)
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '12.5')
    assert resolve_list_read_budget_seconds() == pytest.approx(12.5)
    assert LIST_READ_DEFAULT_BUDGET_SECONDS <= 30 - 6


class _FakeStreamQuery:
    """Query fake whose stream() accepts the per-RPC timeout."""

    def __init__(self, docs: Optional[List[Any]] = None, *, block_until_timeout: bool = False, clock=None):
        self._docs = list(docs or [])
        self._block = block_until_timeout
        self._clock = clock
        self.stream_kwargs: Optional[Dict[str, Any]] = None

    def stream(self, **kwargs):
        self.stream_kwargs = dict(kwargs)
        timeout = kwargs.get('timeout')
        if self._block and timeout is not None:
            # A blocked RPC surfaces exactly at its budget-derived timeout.
            self._clock.advance(timeout)
            raise FirestoreDeadlineExceeded('rpc deadline exceeded')
        yield from self._docs


def test_budgeted_stream_list_passes_derived_timeout_and_charges():
    clock = FakeClock()
    budget = _budget(clock, seconds=10.0)
    query = _FakeStreamQuery([object(), object(), object()])
    docs = budgeted_stream_list(query, budget)
    assert len(docs) == 3
    assert query.stream_kwargs['timeout'] == pytest.approx(10.0)
    assert budget.docs_scanned == 3
    assert not budget.truncated


def test_budgeted_stream_list_maps_firestore_deadline_to_typed_exhaustion():
    clock = FakeClock()
    budget = _budget(clock, seconds=24.0)
    query = _FakeStreamQuery(block_until_timeout=True, clock=clock)
    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        budgeted_stream_list(query, budget)
    assert excinfo.value.reason == 'deadline'
    assert budget.truncated
    # The blocked RPC surfaced at the internal deadline: at least the
    # serialization headroom (30s edge cutoff - 24s internal) remains.
    assert clock.now <= 1_000.0 + 24.0


def test_budgeted_stream_list_falls_back_for_pre_budget_fakes():
    clock = FakeClock()
    budget = _budget(clock, seconds=10.0)

    class _LegacyFake:
        def stream(self):  # no timeout kwarg — predates the budget seam
            return iter([object()])

    docs = budgeted_stream_list(_LegacyFake(), budget)
    assert len(docs) == 1
    assert budget.docs_scanned == 1


def test_budgeted_stream_iter_keeps_partial_rows_before_exhaustion():
    clock = FakeClock()
    budget = _budget(clock, max_documents=2)
    query = _FakeStreamQuery([object(), object(), object(), object()])
    seen = []
    with pytest.raises(ListReadBudgetExhausted):
        for doc in budgeted_stream_iter(query, budget):
            seen.append(doc)
    assert len(seen) == 2  # exactly the rows the allowance covered still ship
    assert budget.exhaustion_reason == 'documents'


def test_budgeted_get_all_charges_returned_snapshots():
    clock = FakeClock()
    budget = _budget(clock)
    client = MagicMock()
    client.get_all.return_value = [object(), object()]
    refs = [object(), object(), object()]
    snapshots = budgeted_get_all(client, refs, budget)
    assert len(snapshots) == 2
    assert budget.docs_scanned == 2
    assert client.get_all.call_args.kwargs.get('timeout') == pytest.approx(24.0)


# ---------------------------------------------------------------------------


def test_telemetry_records_only_route_outcome_and_totals():
    from utils.metrics import (
        LIST_READ_DOCUMENTS_TOTAL,
        LIST_READ_REQUEST_TOTAL,
    )

    clock = FakeClock()
    budget = ListReadBudget(
        deadline_monotonic=clock.now + 24.0,
        max_documents=25_000,
        route='conversations',
        clock=clock,
    )
    budget.charge(7)
    clock.advance(2.0)
    requests_before = LIST_READ_REQUEST_TOTAL.labels(route='conversations', outcome='truncated')._value.get()
    docs_before = LIST_READ_DOCUMENTS_TOTAL.labels(route='conversations')._value.get()
    budget.observe('truncated')
    assert (
        LIST_READ_REQUEST_TOTAL.labels(route='conversations', outcome='truncated')._value.get() == requests_before + 1
    )
    assert LIST_READ_DOCUMENTS_TOTAL.labels(route='conversations')._value.get() == docs_before + 7
    # Label space is bounded to route/outcome — no uid/query/payload labels exist.
    assert set(LIST_READ_REQUEST_TOTAL._labelnames) == {'route', 'outcome'}
    assert set(LIST_READ_DOCUMENTS_TOTAL._labelnames) == {'route'}


def _ai_item(
    item_id: str,
    *,
    completed: bool = False,
    deleted: bool = False,
    created_at: Optional[datetime] = None,
    has_completed_field: bool = True,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        'id': item_id,
        'description': item_id,
        'deleted': deleted,
        'created_at': created_at or datetime(2026, 1, 2, tzinfo=timezone.utc),
        'owner': 'user',
        'source': 'test',
    }
    if has_completed_field:
        data['completed'] = completed
        data['status'] = 'completed' if completed else 'active'
    return data


class _AIDoc:
    def __init__(self, data: Dict[str, Any]):
        self.id = data['id']
        self._data = {k: v for k, v in data.items() if k != 'id'}

    def to_dict(self):
        return dict(self._data)


class _AIQuery:
    def __init__(
        self,
        docs: List[_AIDoc],
        filters=None,
        per_doc_seconds: float = 0.0,
        clock=None,
        stream_error: Optional[BaseException] = None,
    ):
        self._docs = docs
        self._filters = list(filters or [])
        self._per_doc_seconds = per_doc_seconds
        self._clock = clock
        self._stream_error = stream_error

    def where(self, *args, **kwargs):
        filt = kwargs.get('filter') or (args[0] if args else None)
        return _AIQuery(
            self._docs,
            self._filters + [filt],
            self._per_doc_seconds,
            self._clock,
            self._stream_error,
        )

    def order_by(self, *args, **kwargs):
        return self

    def select(self, fields):
        return self

    def limit(self, n):
        return _AILimitQuery(
            self._apply_filters(),
            n,
            self._per_doc_seconds,
            self._clock,
            self._stream_error,
        )

    def _apply_filters(self):
        docs = self._docs
        for filt in self._filters:
            field = getattr(filt, 'field_path', None) or getattr(filt, 'field', None)
            op = getattr(filt, 'op_string', None) or getattr(filt, 'op', '==')
            value = getattr(filt, 'value', None)
            if field == 'completed' and op == '==':
                docs = [d for d in docs if bool(d._data.get('completed', False)) is bool(value)]
            elif field == 'conversation_id' and op == '==':
                docs = [d for d in docs if d._data.get('conversation_id') == value]
        return docs

    def stream(self, **kwargs):
        if self._stream_error is not None and kwargs.get('timeout') is not None:
            raise self._stream_error
        yield from self._apply_filters()


class _AILimitQuery:
    def __init__(self, docs, limit_n, per_doc_seconds, clock, stream_error=None):
        self._docs = docs
        self._limit = limit_n
        self._per_doc_seconds = per_doc_seconds
        self._clock = clock
        self._stream_error = stream_error

    def stream(self, **kwargs):
        if self._stream_error is not None and kwargs.get('timeout') is not None:
            raise self._stream_error
        for doc in self._docs[: self._limit]:
            if self._per_doc_seconds and self._clock is not None:
                self._clock.advance(self._per_doc_seconds)
            yield _AIDoc({'id': doc.id, **doc._data})


@pytest.fixture
def ai_mod(monkeypatch):
    import database.action_items as ai

    monkeypatch.setattr(ai, 'record_firestore_read', lambda *a, **k: None)
    return ai


def _install_ai_db(ai, docs, *, per_doc_seconds: float = 0.0, clock=None, stream_error=None):
    query = _AIQuery(docs, per_doc_seconds=per_doc_seconds, clock=clock, stream_error=stream_error)
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.collection.return_value = query
    ai.db = fake_db


def test_action_items_shares_one_budget_across_active_legacy_and_completed(ai_mod):
    # One active doc (equality bucket), two legacy docs missing the completed
    # field (harvest bucket), three completed docs — every fetched doc must
    # charge the same request budget.
    docs = [
        _AIDoc(_ai_item('active-0', completed=False)),
        _AIDoc(_ai_item('legacy-0', has_completed_field=False)),
        _AIDoc(_ai_item('legacy-1', has_completed_field=False)),
        _AIDoc(_ai_item('done-0', completed=True)),
        _AIDoc(_ai_item('done-1', completed=True)),
        _AIDoc(_ai_item('done-2', completed=True)),
    ]
    clock = FakeClock()
    _install_ai_db(ai_mod, docs)
    budget = _budget(clock, max_documents=25_000)

    page = ai_mod.get_action_items('uid', limit=4, offset=0, budget=budget)

    ids = [item['id'] for item in page]
    # Active-first product order with legacy treated as active.
    assert ids[0] in {'active-0', 'legacy-0', 'legacy-1'}
    assert 'done-0' in ids  # completed fills the remainder of the page
    assert not budget.truncated
    # Equality active query + legacy harvest + completed query all charged.
    assert budget.docs_scanned >= 6


def test_action_items_deadline_cuts_mid_bucket_and_marks_truncated(ai_mod):
    docs = [_AIDoc(_ai_item(f'x{i}', completed=False)) for i in range(200)]
    clock = FakeClock()
    _install_ai_db(ai_mod, docs, per_doc_seconds=1.0, clock=clock)
    budget = _budget(clock, seconds=10.0)

    page = ai_mod.get_action_items('uid', limit=50, offset=0, budget=budget)

    assert budget.truncated
    assert budget.exhaustion_reason == 'deadline'
    # Partial bucket still returns the rows fetched before the cut.
    assert 0 < len(page) < 50


def test_action_items_blocking_rpc_returns_partial_with_headroom(ai_mod):
    docs = [_AIDoc(_ai_item(f'x{i}', completed=False)) for i in range(500)]
    clock = FakeClock()
    _install_ai_db(ai_mod, docs, stream_error=FirestoreDeadlineExceeded('blocked rpc'))
    budget = _budget(clock, seconds=24.0)

    page = ai_mod.get_action_items('uid', limit=50, offset=0, budget=budget)

    assert page == []
    assert budget.truncated
    assert budget.exhaustion_reason == 'deadline'


def test_action_items_non_budget_errors_keep_raising(ai_mod):
    clock = FakeClock()
    _install_ai_db(ai_mod, [], stream_error=FirestoreNotFound('missing document'))
    budget = _budget(clock)

    with pytest.raises(FirestoreNotFound):
        ai_mod.get_action_items('uid', limit=10, offset=0, budget=budget)
    assert not budget.truncated


def test_action_items_route_truncation_surface():

    exhausted = _budget(FakeClock())
    exhausted.mark_exhausted('deadline')
    response_mock = SimpleNamespace(headers={})
    with (
        patch.object(
            action_items_router.action_items_db, 'get_action_items', return_value=[_ai_item('a')]
        ) as get_items,
        patch.object(action_items_router, 'list_read_budget_for_request', return_value=exhausted),
    ):
        result = action_items_router.get_action_items(
            request=None,
            response=response_mock,
            limit=5,
            offset=0,
            completed=None,
            conversation_id=None,
            start_date=None,
            end_date=None,
            due_start_date=None,
            due_end_date=None,
            uid='uid-1',
        )
    assert get_items.call_args.kwargs['budget'] is exhausted
    # Exhaustion: has_more forced true (never "complete" from a missing
    # lookahead) and the documented truncation surface set.
    assert result['has_more'] is True
    assert result['truncated'] is True
    assert response_mock.headers[OMI_LIST_TRUNCATED_HEADER] == OMI_LIST_TRUNCATED_VALUE


def test_action_items_route_parity_on_small_accounts():

    rows = [_ai_item('one'), _ai_item('two')]
    budget = _budget(FakeClock())
    with (
        patch.object(action_items_router.action_items_db, 'get_action_items', return_value=list(rows)),
        patch.object(action_items_router, 'list_read_budget_for_request', return_value=budget),
    ):
        result = action_items_router.get_action_items(
            request=None,
            response=MagicMock(),
            limit=2,
            offset=0,
            completed=None,
            conversation_id=None,
            start_date=None,
            end_date=None,
            due_start_date=None,
            due_end_date=None,
            uid='uid-1',
        )
    assert result == {
        'action_items': result['action_items'],
        'has_more': False,
        'truncated': False,
    }
    assert [item.id for item in result['action_items']] == ['one', 'two']


# ---------------------------------------------------------------------------
# C. Conversations — offset charged before the query; large-N offsets
# ---------------------------------------------------------------------------


def _conv_doc(index: int) -> _AIDoc:
    return _AIDoc(
        {
            'id': f'conv-{index:06d}',
            'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index),
            'status': 'completed',
        }
    )


class _ConvQuery:
    def __init__(self, docs, *, offset=0, limit_n=None, per_doc_seconds=0.0, clock=None, recorder=None):
        self._docs = docs
        self._offset = offset
        self._limit = limit_n
        self._per_doc_seconds = per_doc_seconds
        self._clock = clock
        self._recorder = recorder

    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        return _ConvQuery(
            self._docs,
            offset=self._offset,
            limit_n=n,
            per_doc_seconds=self._per_doc_seconds,
            clock=self._clock,
            recorder=self._recorder,
        )

    def offset(self, n):
        return _ConvQuery(
            self._docs,
            offset=n,
            limit_n=self._limit,
            per_doc_seconds=self._per_doc_seconds,
            clock=self._clock,
            recorder=self._recorder,
        )

    def stream(self, **kwargs):
        timeout = kwargs.get('timeout')
        if timeout is not None and self._recorder is not None:
            self._recorder['streams'] = self._recorder['streams'] + 1
        docs = self._docs[self._offset :]
        if self._limit is not None:
            docs = docs[: self._limit]
        for doc in docs:
            if self._per_doc_seconds and self._clock is not None:
                self._clock.advance(self._per_doc_seconds)
            yield _AIDoc({'id': doc.id, **doc._data})


@pytest.fixture
def conv_mod(monkeypatch):
    import database.conversations as conv

    # Skip the decrypt decorator's data-protection backfill network calls.
    monkeypatch.setattr(conv, '_prepare_conversation_for_read', lambda data, uid: data)
    monkeypatch.setattr(conv, '_document_data_with_revision', lambda doc: doc.to_dict() | {'id': doc.id})
    return conv


def _install_conv_db(conv, docs, *, per_doc_seconds=0.0, clock=None, recorder=None):
    query = _ConvQuery(docs, per_doc_seconds=per_doc_seconds, clock=clock, recorder=recorder)
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.collection.return_value = query
    conv.db = fake_db


@pytest.mark.parametrize('total,offset,limit', [(1_000, 900, 100), (5_000, 4_900, 100), (20_000, 19_000, 1_000)])
def test_conversations_large_offsets_are_served_and_charged(conv_mod, total, offset, limit):
    docs = [_conv_doc(i) for i in range(total)]
    clock = FakeClock()
    _install_conv_db(conv_mod, docs)
    budget = _budget(clock, max_documents=25_000)

    page = conv_mod.get_conversations_without_photos('uid', limit, offset, budget=budget)

    assert len(page) == limit
    assert page[0]['id'] == f'conv-{offset:06d}'
    assert not budget.truncated
    # The skipped offset prefix is charged before the page rows.
    assert budget.docs_scanned == offset + limit


def test_conversations_deadline_cut_keeps_honest_prefix(conv_mod):
    docs = [_conv_doc(i) for i in range(1_000)]
    clock = FakeClock()
    _install_conv_db(conv_mod, docs, per_doc_seconds=0.5, clock=clock)
    budget = _budget(clock, seconds=10.0)

    page = conv_mod.get_conversations_without_photos('uid', 100, 0, budget=budget)

    assert budget.truncated
    assert 0 < len(page) < 100
    # Created-at DESC prefix: the emitted rows are the newest ones.
    assert page[0]['id'] == 'conv-000000'


def test_conversations_parity_without_budget(conv_mod):
    docs = [_conv_doc(i) for i in range(5)]
    _install_conv_db(conv_mod, docs)
    unbudgeted = conv_mod.get_conversations_without_photos('uid', 3, 1)
    budgeted = conv_mod.get_conversations_without_photos('uid', 3, 1, budget=_budget(FakeClock()))
    assert [row['id'] for row in unbudgeted] == [row['id'] for row in budgeted]


def test_conversations_route_sets_header_only_when_truncated():

    truncated_budget = _budget(FakeClock())
    truncated_budget.mark_exhausted('deadline')
    complete_budget = _budget(FakeClock())
    for budget, expect_header in ((truncated_budget, True), (complete_budget, False)):
        response_mock = MagicMock()
        with (
            patch.object(
                conversations_router.conversations_db,
                'get_conversations_without_photos',
                return_value=[],
            ),
            patch.object(conversations_router, 'list_read_budget_for_request', return_value=budget),
        ):
            conversations_router.get_conversations(
                request=None,
                response=response_mock,
                limit=100,
                offset=0,
                statuses='completed',
                include_discarded=True,
                sources=None,
                start_date=None,
                end_date=None,
                folder_id=None,
                starred=None,
                uid='uid-1',
            )
        header_calls = [
            call
            for call in response_mock.headers.__setitem__.call_args_list
            if call.args[:1] == (OMI_LIST_TRUNCATED_HEADER,)
        ]
        assert bool(header_calls) is expect_header


def test_conversations_offset_beyond_allowance_truncates_without_querying(conv_mod):
    # The offset charge happens before any stream, so a tiny collection is
    # enough to prove the allowance gate.
    docs = [_conv_doc(i) for i in range(10)]
    recorder = {'streams': 0}
    clock = FakeClock()
    _install_conv_db(conv_mod, docs, recorder=recorder)
    budget = _budget(clock, max_documents=25_000)

    page = conv_mod.get_conversations_without_photos('uid', 100, 30_000, budget=budget)

    assert page == []
    assert budget.truncated
    assert budget.exhaustion_reason == 'documents'
    # No Firestore stream may start once the offset consumed the allowance.
    assert recorder['streams'] == 0


# ---------------------------------------------------------------------------
# D. Memories — budgeted read_page and shared-budget fallback
# ---------------------------------------------------------------------------


@pytest.fixture
def service_mod(monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "read")
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "unit-test-list-budget-secret")
    from tests.unit.test_memory_service_parity import _load_memory_service

    module = _load_memory_service(monkeypatch)
    yield module
    # The focused tests replace imported module-level seams directly.
    for name in ("read_canonical_scan_page",):
        import utils.memory.canonical_memory_adapter as adapter

        setattr(module, name, adapter.read_canonical_scan_page)


def _memory(service_mod, memory_id: str, *, day: int):
    from tests.unit.test_universal_memory_service import _memory as build_memory

    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
    return build_memory(service_mod, memory_id).model_copy(update={"updated_at": stamp, "created_at": stamp})


def _dated_historical(service_mod, memory_id: str, *, day: int):
    memory = _memory(service_mod, memory_id, day=day)
    return service_mod.HistoricalMemoryRecord(
        memory=memory,
        locator=service_mod.MemoryLocator("uid-test", "legacy", memory_id),
    )


def _scan_cursor_for(memory):
    return (memory.updated_at, memory.id)


def _install_streams(service, service_mod, *, canonical, historical, statuses=None):
    ordered = sorted(
        list(canonical),
        key=lambda memory: (-memory.updated_at.timestamp(), memory.id),
    )

    def fake_canonical_scan(
        _uid,
        *,
        limit,
        start_after=None,
        db_client=None,
        device_scope_request=None,
        include_pending_processing=False,
        include_archive=False,
        now=None,
        budget=None,
    ):
        del db_client, device_scope_request, include_pending_processing, include_archive, now
        start = 0
        if start_after is not None:
            cursor_time, cursor_id = start_after
            cursor_key = (-cursor_time.timestamp(), cursor_id)
            start = next(
                (
                    index
                    for index, memory in enumerate(ordered)
                    if (-memory.updated_at.timestamp(), memory.id) > cursor_key
                ),
                len(ordered),
            )
        chunk = ordered[start : start + limit]
        if budget is not None:
            # Mirror the real fetch seam: every fetched row (emitted or
            # filtered) charges the request budget and can exhaust it.
            budget.charge(len(chunk))
        slots = [(memory, _scan_cursor_for(memory)) for memory in chunk]
        exhausted = len(chunk) < limit or (start + len(chunk)) >= len(ordered)
        return slots, exhausted

    service_mod.read_canonical_scan_page = MagicMock(side_effect=fake_canonical_scan)

    def _keyset_page(rows, *, limit, start_after, order_attr):
        start = 0
        if start_after is not None:
            cursor_time, cursor_id = start_after
            cursor_key = (-cursor_time.timestamp(), cursor_id)
            start = next(
                (
                    index
                    for index, record in enumerate(rows)
                    if (-getattr(record.memory, order_attr).timestamp(), record.memory.id) > cursor_key
                ),
                len(rows),
            )
        chunk = rows[start : start + limit]
        slots = [(record, (getattr(record.memory, order_attr), record.memory.id)) for record in chunk]
        exhausted = len(chunk) < limit or (start + len(chunk)) >= len(rows)
        return slots, exhausted

    def _charging_keyset_page(rows, *, limit, start_after, order_attr, budget):
        chunk_result = _keyset_page(rows, limit=limit, start_after=start_after, order_attr=order_attr)
        if budget is not None:
            # Mirror the real fetch seam: fetched rows charge the request budget.
            budget.charge(len(chunk_result[0]))
        return chunk_result

    ordered_historical = sorted(
        list(historical),
        key=lambda record: (-record.memory.updated_at.timestamp(), record.memory.id),
    )
    service.history.read_updated_scan_page = MagicMock(
        side_effect=lambda _uid, *, limit, start_after=None, device_scope_request=None, budget=None: (
            _charging_keyset_page(
                ordered_historical,
                limit=limit,
                start_after=start_after,
                order_attr="updated_at",
                budget=budget,
            )
        )
    )
    service.history.read_created_scan_page = MagicMock(return_value=([], True))
    service.canonical_statuses = MagicMock(return_value=statuses or {})


def test_read_page_parent_exhaustion_returns_partial_page_without_cursor(service_mod):
    from tests.unit.test_universal_memory_service import _Db

    service = service_mod.MemoryService(db_client=_Db())
    historical = [_dated_historical(service_mod, f"h-{index}", day=100 - index) for index in range(30)]
    _install_streams(service, service_mod, canonical=[], historical=historical)
    clock = FakeClock()
    # The parent allowance ends the merge well before the 30-row page fills;
    # the scan sub-budget (4000 rows / 6s) is nowhere near its own bounds.
    budget = _budget(clock, seconds=60.0, max_documents=5)

    page = service.read_page("uid-test", limit=30, cursor=None, request_budget=budget)

    assert budget.truncated
    assert page.truncated is True
    # Items already merged are an honest prefix of the newest-first order…
    assert [memory.id for memory in page.memories] == [f"h-{index}" for index in range(len(page.memories))]
    # …but no resumable cursor: scan positions are not fully covered.
    assert page.next_cursor is None
    assert len(page.memories) < 30


def test_read_page_complete_page_keeps_cursor_when_budgeted(service_mod):
    from tests.unit.test_universal_memory_service import _Db

    service = service_mod.MemoryService(db_client=_Db())
    historical = [_dated_historical(service_mod, f"h-{index}", day=100 - index) for index in range(10)]
    _install_streams(service, service_mod, canonical=[], historical=historical)
    clock = FakeClock()
    budget = _budget(clock)

    page = service.read_page("uid-test", limit=4, cursor=None, request_budget=budget)

    assert not page.truncated
    assert page.next_cursor  # lossless continuation is advertised when complete
    assert [memory.id for memory in page.memories] == ["h-0", "h-1", "h-2", "h-3"]


class _IndexSnapshot:
    def __init__(self, doc_id: str, data: Dict[str, Any]):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _IndexQuery:
    """Fake memories-collection query honoring the index read shape."""

    def __init__(self, docs: Dict[str, Dict[str, Any]]):
        self._docs = docs
        self._order_field = 'updated_at'
        self._limit = None

    def select(self, fields):
        del fields
        return self

    def order_by(self, field, direction=None):
        del direction
        self._order_field = field
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _ordered_rows(self):
        def sort_key(item):
            doc_id, data = item
            value = data.get(self._order_field)
            if isinstance(value, str):
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if not isinstance(value, datetime):
                value = datetime.min.replace(tzinfo=timezone.utc)
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return -value.timestamp(), doc_id

        return sorted(self._docs.items(), key=sort_key)

    def stream(self, **kwargs):
        del kwargs
        rows = self._ordered_rows()
        if self._limit is not None:
            rows = rows[: self._limit]
        for doc_id, data in rows:
            yield _IndexSnapshot(doc_id, data)


class _MemoriesIndexClient:
    """Firestore client fake for users/{uid}/memories index reads."""

    def __init__(self, docs: Dict[str, Dict[str, Any]]):
        self.docs = docs

    def collection(self, name):
        assert name == 'users'
        client = self

        class _MemoriesCollection:
            def select(self, fields):
                del fields
                return _IndexQuery(client.docs)

            def document(self, memory_id):
                return SimpleNamespace(path=f"users/uid-test/memories/{memory_id}")

        class _UserDocument:
            def collection(self, collection_name):
                assert collection_name == 'memories'
                return _MemoriesCollection()

        class _UsersCollection:
            def document(self, uid):
                del uid
                return _UserDocument()

        return _UsersCollection()

    def get_all(self, refs, **kwargs):
        del kwargs
        for ref in refs:
            memory_id = ref.path.rsplit('/', 1)[-1]
            payload = self.docs.get(memory_id)
            if payload is not None:
                yield _IndexSnapshot(memory_id, payload)


def _suppressed_read_client(rows: int) -> _MemoriesIndexClient:
    from tests.unit.test_memory_service_parity import _sample_memory_dict

    docs: Dict[str, Dict[str, Any]] = {}
    for index in range(rows):
        payload = dict(_sample_memory_dict(f"hist-{index:05d}"))
        payload["updated_at"] = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=rows - index)
        docs[f"hist-{index:05d}"] = payload
    return _MemoriesIndexClient(docs)


def _real_index_helpers(service_mod, monkeypatch, client):
    """Undo the parity harness's []-stubs so the real index path runs."""
    monkeypatch.setattr(
        service_mod.memories_db,
        "list_memory_updated_or_created_index",
        service_mod._prod_list_memory_updated_or_created_index,
    )

    def fake_by_ids(_uid, ids, **_kwargs):
        del _uid
        return [dict(client.docs[memory_id]) for memory_id in ids if memory_id in client.docs]

    monkeypatch.setattr(service_mod.memories_db, "get_memories_by_ids", fake_by_ids)


def test_offset_read_charges_dual_windows_and_emitted_rows(service_mod, monkeypatch):
    client = _suppressed_read_client(rows=200)
    monkeypatch.setattr(service_mod, "read_canonical_memories", lambda *a, **k: [])
    _real_index_helpers(service_mod, monkeypatch, client)
    service = service_mod.MemoryService(db_client=client)
    service.canonical_statuses = MagicMock(return_value={})
    clock = FakeClock()
    budget = _budget(clock, max_documents=25_000)

    memories = service.read("uid-test", limit=50, offset=0, budget=budget)

    assert len(memories) == 50
    assert not budget.truncated
    # The index read streams two candidate windows (updated_at DESC and
    # created_at DESC); every fetched row of both charged the request budget.
    assert budget.docs_scanned >= 100


def test_offset_read_parent_exhaustion_returns_partial_and_stops_scanning(service_mod, monkeypatch):
    client = _suppressed_read_client(rows=5_000)
    monkeypatch.setattr(service_mod, "read_canonical_memories", lambda *a, **k: [])
    _real_index_helpers(service_mod, monkeypatch, client)
    service = service_mod.MemoryService(db_client=client)
    service.canonical_statuses = MagicMock(return_value={})
    clock = FakeClock()
    # Allowance smaller than one dual-window round: the offset read must stop
    # at the allowance instead of expanding into fresh unbudgeted windows.
    budget = _budget(clock, seconds=60.0, max_documents=40)

    memories = service.read("uid-test", limit=50, offset=0, budget=budget)

    assert budget.truncated
    assert budget.exhaustion_reason == 'documents'
    # Fewer rows than the requested page — the scan stopped at the allowance.
    assert len(memories) < 50


def test_memories_route_marks_truncation_and_suppresses_next_cursor():

    page = SimpleNamespace(
        memories=[],
        next_cursor='uml.should-not-appear',
        truncated=True,
    )
    service = MagicMock()
    service.read_page.return_value = page
    scope_request = SimpleNamespace(device_scope='all', client_device_id=None)
    response_mock = MagicMock()
    budget = _budget(FakeClock())
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope_request),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(mem_mod, 'list_read_budget_for_request', return_value=budget),
    ):
        result = mem_mod.get_memories(
            response=response_mock,
            request=None,
            limit=100,
            offset=0,
            cursor=None,
            include_archive=False,
            device_scope='all',
            client_device_id=None,
            uid='uid1',
            x_app_platform=None,
            x_device_id_hash=None,
        )
    body = json.loads(result.body)
    assert body == []
    headers = {k.lower(): v for k, v in result.headers.items()}
    assert headers['x-omi-list-truncated'] == 'true'
    assert 'x-omi-memory-next-cursor' not in headers
    # The budget was shared into the keyset scan.
    assert service.read_page.call_args.kwargs['request_budget'] is budget


def test_memories_route_complete_page_keeps_cursor_header():

    page = SimpleNamespace(
        memories=[],
        next_cursor='uml.next',
        truncated=False,
    )
    service = MagicMock()
    service.read_page.return_value = page
    scope_request = SimpleNamespace(device_scope='all', client_device_id=None)
    budget = _budget(FakeClock())
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope_request),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(mem_mod, 'list_read_budget_for_request', return_value=budget),
    ):
        result = mem_mod.get_memories(
            response=MagicMock(),
            request=None,
            limit=100,
            offset=0,
            cursor=None,
            include_archive=False,
            device_scope='all',
            client_device_id=None,
            uid='uid1',
            x_app_platform=None,
            x_device_id_hash=None,
        )
    headers = {k.lower(): v for k, v in result.headers.items()}
    assert headers.get('x-omi-memory-next-cursor') == 'uml.next'
    assert 'x-omi-list-truncated' not in headers


def test_memories_route_scan_budget_fallback_shares_the_request_budget():
    """Scan-budget 503 still falls back to the offset read — on the same budget."""
    from fastapi import HTTPException

    service = MagicMock()
    service.read_page.side_effect = HTTPException(status_code=503, detail=mem_mod.MEMORY_LIST_SCAN_BUDGET_DETAIL)
    service.read.return_value = []
    scope_request = SimpleNamespace(device_scope='all', client_device_id=None)
    budget = _budget(FakeClock())
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope_request),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(mem_mod, 'list_read_budget_for_request', return_value=budget),
    ):
        result = mem_mod.get_memories(
            response=MagicMock(),
            request=None,
            limit=100,
            offset=0,
            cursor=None,
            include_archive=False,
            device_scope='all',
            client_device_id=None,
            uid='uid1',
            x_app_platform=None,
            x_device_id_hash=None,
        )
    # The fallback read ran, and it carried the SAME budget object — never a
    # fresh unbudgeted window.
    assert service.read.call_args.kwargs['budget'] is budget
    headers = {k.lower(): v for k, v in result.headers.items()}
    assert 'x-omi-list-truncated' not in headers
