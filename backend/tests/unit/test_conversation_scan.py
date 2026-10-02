"""The shared single-pass conversation scan and its read-count contract.

The retired People/speaker scan fetched each page through
``database.conversations._collect_visible_conversation_page`` with
``include_discarded=True``: every page restarts its stream at the newest row
and skips ``offset`` already-returned rows in Python, so ten 100-row pages
re-read 100+200+...+1000 = 5,500 raw documents to surface 1,000 visible rows
— the production People-list timeout. ``iter_conversations`` replaces that
with one bounded, snapshot-cursor pass: ten queries of ``limit(100)`` read
exactly 1,000 documents for the same window, and a required ``ListReadBudget``
bounds raw documents and wall-clock so an exhausted request returns its
honest prefix marked truncated.

Everything here is hermetic: ``_StrictClient`` evaluates the real query
recipe (filters, ordering, ``start_after`` snapshots, projections) in memory
and refuses offset and unbounded streams; the historical baseline is measured
by calling the real retired helper against a permissive counting fake.
"""

from __future__ import annotations

import json
import os
import zlib

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core import exceptions as api_exceptions
from google.api_core import retry as api_retry
from google.api_core.exceptions import DeadlineExceeded
from google.cloud import firestore

import database.conversation_scan as conversation_scan
import database.conversations as conversations_db
import routers.users as users_router
import routers.conversations as conversations_router
import utils.other.endpoints as auth_endpoints
import utils.encryption as encryption
from database.conversation_scan import (
    PEOPLE_STATS_FIELD_PATHS,
    conversation_scan_budget,
    iter_conversations,
)
from database.conversations import (
    _collect_visible_conversation_page,
    encode_conversation_for_write,
    prepare_conversation_for_read,
)
from utils.other.list_budget import (
    OMI_LIST_TRUNCATED_HEADER,
    REQUEST_STARTED_MONOTONIC_STATE_KEY,
    ListReadBudget,
    resolve_list_read_budget_seconds,
    resolve_list_read_max_documents,
)
from utils.people_stats import aggregate_people_stats, collect_people_stats
from utils.conversations.search import browse_conversations_by_speaker

UID = 'u1'
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_MISSING = object()


def _segments(person_id: Optional[str] = 'p1', **extra) -> list:
    return [
        {
            'id': 's0',
            'speaker_id': 0,
            'is_user': False,
            'person_id': person_id,
            'start': 0,
            'end': 2,
            'text': 'hi',
            **extra,
        }
    ]


def _stored(doc_id: str, i: int = 0, **extra) -> Dict[str, Any]:
    return {
        'id': doc_id,
        'created_at': T0 - timedelta(seconds=i),
        'started_at': T0 - timedelta(seconds=i),
        'finished_at': T0 - timedelta(seconds=i) + timedelta(seconds=2),
        'structured': {},
        'discarded': False,
        'data_protection_level': 'standard',
        'transcript_segments': _segments(),
        **extra,
    }


class _Snap:
    """Stand-in ``DocumentSnapshot``: the reader only needs id/to_dict/update_time."""

    def __init__(self, path: str, data: Optional[dict]):
        self.reference = SimpleNamespace(path=path)
        self.id = path.rsplit('/', 1)[-1]
        self.exists = data is not None
        self.update_time = None
        self._data = data

    def to_dict(self) -> Optional[dict]:
        return dict(self._data) if self._data is not None else None


class _StrictClient:
    """Evaluates the real query recipe in memory and refuses anything else.

    ``offset`` raises, ``stream`` requires the budget timeout and a retry that
    excludes deadlines, and a query without a positive server-side ``limit``
    never reaches the wire.
    """

    def __init__(self, uid: str, docs: List[dict], tick=None):
        self.uid = uid
        self.snaps = [_Snap(f'users/{uid}/conversations/{doc["id"]}', doc) for doc in docs]
        self.tick = tick
        self.queries: List[dict] = []
        self.raw_reads = 0
        self.streams_abandoned = 0

    def collection(self, name: str):
        assert name == 'users'
        return _UsersColl(self)


class _UsersColl:
    def __init__(self, client: _StrictClient):
        self._client = client

    def document(self, uid: str):
        return _UserDoc(self._client, uid)


class _UserDoc:
    def __init__(self, client: _StrictClient, uid: str):
        self._client = client
        self._uid = uid

    def collection(self, name: str):
        assert name == 'conversations'
        return _StrictQuery(self._client)


class _StrictQuery:
    def __init__(
        self,
        client: _StrictClient,
        filters: tuple = (),
        descending: bool = False,
        bound: Optional[int] = None,
        projection: Optional[tuple] = None,
        cursor: Optional[_Snap] = None,
    ):
        self._client = client
        self._filters = filters
        self._descending = descending
        self._bound = bound
        self._projection = projection
        self._cursor = cursor

    def _clone(self, **changes) -> '_StrictQuery':
        state = {
            'filters': self._filters,
            'descending': self._descending,
            'bound': self._bound,
            'projection': self._projection,
            'cursor': self._cursor,
        }
        state.update(changes)
        return _StrictQuery(self._client, **state)

    def where(self, *args, filter=None, **kwargs):
        assert filter is not None and not args and not kwargs, 'reader must use FieldFilter'
        return self._clone(filters=self._filters + (filter,))

    def order_by(self, field_path: str, direction=None):
        assert field_path == 'created_at'
        assert direction == firestore.Query.DESCENDING
        return self._clone(descending=True)

    def select(self, field_paths):
        return self._clone(projection=tuple(field_paths))

    def limit(self, count: int):
        assert isinstance(count, int) and count > 0
        return self._clone(bound=count)

    def offset(self, *_args):
        raise AssertionError('the scan reader must never use offset')

    def start_after(self, snapshot):
        assert isinstance(snapshot, _Snap)
        return self._clone(cursor=snapshot)

    def _matches(self, snap: _Snap) -> bool:
        data = snap._data
        for node in self._filters:
            value = data.get(node.field_path, _MISSING)
            if value is _MISSING:
                # Firestore filters never match documents missing the field.
                return False
            op = str(getattr(node.op_string, 'name', None) or node.op_string)
            if op == '==':
                matched = value == node.value
            elif op == '>=':
                matched = value >= node.value
            elif op == '<=':
                matched = value <= node.value
            else:
                raise AssertionError(f'unexpected operator {op}')
            if not matched:
                return False
        return True

    def _evaluate(self) -> List[_Snap]:
        rows = [snap for snap in self._client.snaps if self._matches(snap)]
        # created_at desc with __name__ as the implicit tiebreaker.
        rows.sort(key=lambda snap: (snap._data['created_at'], snap.id), reverse=True)
        if self._cursor is not None:
            index = next(i for i, snap in enumerate(rows) if snap.id == self._cursor.id)
            rows = rows[index + 1 :]
        rows = rows[: self._bound]
        if self._projection is None:
            return rows
        return [
            _Snap(snap.reference.path, {k: v for k, v in snap._data.items() if k in self._projection}) for snap in rows
        ]

    def stream(self, **kwargs):
        timeout = kwargs.get('timeout')
        assert (
            timeout is not None and 0 < timeout <= conversation_scan.CONVERSATION_SCAN_SECONDS
        ), 'stream timeout must be a positive budget bound'
        retry = kwargs.get('retry')
        assert isinstance(retry, api_retry.Retry), 'scan streams must pass their own retry'
        assert not retry._predicate(
            api_exceptions.DeadlineExceeded('budget')
        ), 'a deadline must end the scan, not restart the timeout'
        assert retry._predicate(api_exceptions.ServiceUnavailable('transient')), 'transient failures still retry'
        assert self._bound is not None, 'unbounded query: missing limit'
        self._client.queries.append(
            {'limit': self._bound, 'cursor': self._cursor is not None, 'projection': self._projection}
        )
        results = self._evaluate()
        tick = self._client.tick

        def generate():
            completed = False
            try:
                for snap in results:
                    self._client.raw_reads += 1
                    if tick is not None:
                        tick()
                    yield snap
                completed = True
            finally:
                if not completed:
                    self._client.streams_abandoned += 1

        return generate()


class _LegacyCountingRef:
    """Permissive stand-in for the retired helper: streams everything, unbounded.

    Exists only to measure the historical repeated-prefix cost; the new reader
    is pinned against ``_StrictClient`` instead.
    """

    def __init__(self, snaps: List[_Snap]):
        self._snaps = snaps
        self.streams = 0
        self.raw_reads = 0

    def stream(self):
        self.streams += 1
        for snap in self._snaps:
            self.raw_reads += 1
            yield snap


def _budget(max_documents: int = 2000, seconds: float = 12.0, clock=None) -> ListReadBudget:
    now = clock() if clock else 1000.0
    return ListReadBudget(
        deadline_monotonic=now + seconds,
        max_documents=max_documents,
        clock=clock or (lambda: now),
        started_monotonic=now,
    )


def _scan(docs, *, clock=None, tick=None, **kwargs):
    client = _StrictClient(UID, docs, tick=tick)
    kwargs.setdefault('budget', _budget(clock=clock))
    return client, list(iter_conversations(UID, firestore_client=client, **kwargs))


# ---------------------------------------------------------------------------
# The historical before/after read-count contract
# ---------------------------------------------------------------------------


def test_legacy_repeated_prefix_scan_reads_5500_rows_across_10_streams():
    """The retired ``include_discarded=True`` page fetch re-read from the newest row."""
    snaps = [_Snap(f'users/{UID}/conversations/c{i}', _stored(f'c{i}', i)) for i in range(1200)]
    ref = _LegacyCountingRef(snaps)
    for offset in range(0, 1000, 100):
        page = _collect_visible_conversation_page(ref, limit=100, offset=offset, include_discarded=True, budget=None)
        assert len(page) == 100
    assert ref.streams == 10
    # 100 + 200 + ... + 1000: every page re-read the full prefix it then skipped.
    assert ref.raw_reads == 5500


def test_single_pass_scan_reads_1000_rows_across_10_bounded_queries():
    """The replacement: one cursor pass, never offset, never unbounded."""
    docs = [_stored(f'c{i}', i) for i in range(1200)]
    client, conversations = _scan(docs, limit=1000, batch=100)
    assert len(conversations) == 1000
    assert client.raw_reads == 1000
    assert len(client.queries) == 10
    assert all(query['limit'] == 100 for query in client.queries)
    # Only the first page lacks a cursor; every later page resumes by snapshot.
    assert [query['cursor'] for query in client.queries] == [False] + [True] * 9


def test_scan_stats_match_the_window_the_legacy_scan_covered():
    docs = [_stored(f'c{i}', i) for i in range(1200)]
    client = _StrictClient(UID, docs)
    stats = collect_people_stats(
        iter_conversations(UID, limit=1000, batch=100, budget=_budget(), firestore_client=client)
    )
    assert stats['p1']['conversation_count'] == 1000
    assert client.raw_reads == 1000


# ---------------------------------------------------------------------------
# Visibility, cursors, and budgets
# ---------------------------------------------------------------------------


def test_invisible_rows_advance_the_cursor_without_ending_the_scan():
    # deleted tombstones and discarded rows sit inside the first window; the
    # scan must reach past them rather than treating a thin page as the end.
    no_discarded_field = {k: v for k, v in _stored('missing-discarded-field', 4).items() if k != 'discarded'}
    docs = (
        [_stored('visible-1', 0), _stored('tombstone', 1, deleted=True)]
        + [_stored('visible-2', 2)]
        + [_stored('discarded-1', 3, discarded=True)]
        + [no_discarded_field]
        + [_stored('locked-visible', 5, is_locked=True)]
        + [_stored('visible-3', 6)]
    )
    client, conversations = _scan(docs, limit=10, batch=2)
    ids = [c['id'] for c in conversations]
    assert ids == ['visible-1', 'visible-2', 'locked-visible', 'visible-3']
    # 5 raw rows over 3 pages: discarded/missing-field rows are filtered
    # server-side, the deleted tombstone streams and is skipped in Python.
    assert client.raw_reads == 5
    assert len(client.queries) == 3
    # Aggregation excludes every invisible row: the tombstone and discarded row
    # never arrive, and the yielded locked row is ignored by the aggregator.
    stats = aggregate_people_stats(conversations)
    assert stats['p1']['conversation_count'] == 3


def test_stats_reads_only_to_the_raw_budget_through_mostly_deleted_rows():
    # One valid row, 2,000 tombstones, one more valid row: the 2,000-document
    # raw allowance stops exactly before the second valid row.
    docs = [_stored('v0', 0)] + [_stored(f'd{i}', 1 + i, deleted=True) for i in range(2000)] + [_stored('v1', 2001)]
    budget = _budget(max_documents=2000)
    client = _StrictClient(UID, docs)
    stats = collect_people_stats(iter_conversations(UID, limit=1000, batch=100, budget=budget, firestore_client=client))
    assert client.raw_reads == 2000
    assert stats['p1']['conversation_count'] == 1  # only v0; v1 is beyond the allowance
    assert budget.truncated and budget.exhaustion_reason == 'documents'


def test_start_after_snapshot_ties_on_created_at_still_advance():
    # Two rows sharing created_at must not be skipped or re-yielded by the cursor.
    docs = [_stored('first', 0), _stored('second', 0)]
    client, conversations = _scan(docs, limit=10, batch=1)
    assert sorted(c['id'] for c in conversations) == ['first', 'second']
    assert len(client.queries) == 3  # two full single-row pages + the empty tail


def test_document_budget_caps_raw_reads_and_marks_truncation():
    docs = [_stored(f'c{i}', i) for i in range(2500)]
    budget = _budget(max_documents=2000)
    client = _StrictClient(UID, docs)
    conversations = list(iter_conversations(UID, limit=2500, batch=100, budget=budget, firestore_client=client))
    assert client.raw_reads == 2000
    assert len(conversations) == 2000
    assert budget.truncated and budget.exhaustion_reason == 'documents'


def test_exact_page_boundary_consumes_the_allowance_and_still_truncates():
    docs = [_stored(f'c{i}', i) for i in range(6)]
    # The whole allowance lands on one full page, so the reader must stop
    # before issuing another query even though the target is not reached.
    budget = _budget(max_documents=5)
    client = _StrictClient(UID, docs)
    conversations = list(iter_conversations(UID, limit=10, batch=5, budget=budget, firestore_client=client))
    assert len(conversations) == 5
    assert len(client.queries) == 1
    assert budget.truncated and budget.exhaustion_reason == 'documents'


def test_visible_cap_at_normal_page_count_does_not_mark_exhaustion():
    docs = [_stored(f'c{i}', i) for i in range(250)]
    budget = _budget(max_documents=2000)
    client = _StrictClient(UID, docs)
    conversations = list(iter_conversations(UID, limit=200, batch=100, budget=budget, firestore_client=client))
    assert len(conversations) == 200
    assert not budget.truncated


def test_deadline_before_first_query_returns_empty_prefix():
    now = [1000.0]
    budget = ListReadBudget(deadline_monotonic=900.0, max_documents=2000, clock=lambda: now[0], started_monotonic=900.0)
    client = _StrictClient(UID, [_stored('c0', 0)])
    conversations = list(iter_conversations(UID, budget=budget, firestore_client=client))
    assert conversations == []
    assert client.queries == []
    assert budget.truncated and budget.exhaustion_reason == 'deadline'


def test_deadline_mid_stream_returns_the_honest_prefix():
    clock_now = [1000.0]
    budget = ListReadBudget(
        deadline_monotonic=1008.0, max_documents=2000, clock=lambda: clock_now[0], started_monotonic=1000.0
    )
    docs = [_stored(f'c{i}', i) for i in range(10)]
    # Tick advances the shared clock by 5s per delivered row; the second
    # row's charge lands past the 8s deadline, so the prefix is one row.
    client = _StrictClient(UID, docs, tick=lambda: clock_now.__setitem__(0, clock_now[0] + 5))
    conversations = list(iter_conversations(UID, limit=10, batch=10, budget=budget, firestore_client=client))
    assert len(conversations) == 1
    assert budget.truncated and budget.exhaustion_reason == 'deadline'


def test_deadline_exceeded_from_the_rpc_returns_the_prefix():
    calls = [0]

    def fail_after_two():
        calls[0] += 1
        if calls[0] == 3:
            raise DeadlineExceeded('rpc timed out')

    docs = [_stored(f'c{i}', i) for i in range(10)]
    budget = _budget()
    client = _StrictClient(UID, docs, tick=fail_after_two)
    conversations = list(iter_conversations(UID, limit=10, batch=10, budget=budget, firestore_client=client))
    assert len(conversations) == 2
    assert budget.truncated and budget.exhaustion_reason == 'deadline'


def test_decode_past_the_deadline_never_yields_that_row(monkeypatch):
    """Decode consumes budget time: a row prepared past the deadline must not ship."""
    clock_now = [1000.0]
    budget = ListReadBudget(
        deadline_monotonic=1005.0, max_documents=2000, clock=lambda: clock_now[0], started_monotonic=1000.0
    )
    real_prepare = conversation_scan.prepare_conversation_for_read
    calls = [0]

    def slow_decode(raw, uid):
        calls[0] += 1
        if calls[0] == 2:
            clock_now[0] += 10.0  # the second row's decode overruns the deadline
        return real_prepare(raw, uid)

    monkeypatch.setattr(conversation_scan, 'prepare_conversation_for_read', slow_decode)
    client = _StrictClient(UID, [_stored('c0', 0), _stored('c1', 1)])
    conversations = list(iter_conversations(UID, limit=10, batch=10, budget=budget, firestore_client=client))
    assert [c['id'] for c in conversations] == ['c0']
    assert budget.truncated and budget.exhaustion_reason == 'deadline'


def test_closing_the_reader_releases_the_underlying_stream():
    docs = [_stored(f'c{i}', i) for i in range(10)]
    client = _StrictClient(UID, docs)
    reader = iter_conversations(UID, limit=10, batch=10, budget=_budget(), firestore_client=client)
    next(reader)
    reader.close()
    assert client.streams_abandoned == 1


def test_budget_exhaustion_closes_the_stream():
    # A mid-stream deadline raises inside the stream wrapper with rows still
    # behind the cursor; the wrapper's finally must release the fake stream.
    docs = [_stored(f'c{i}', i) for i in range(10)]
    clock_now = [1000.0]
    client = _StrictClient(UID, docs, tick=lambda: clock_now.__setitem__(0, clock_now[0] + 5.0))
    budget = ListReadBudget(
        deadline_monotonic=1012.0,
        max_documents=2000,
        clock=lambda: clock_now[0],
        started_monotonic=1000.0,
    )
    conversations = list(iter_conversations(UID, limit=10, batch=10, budget=budget, firestore_client=client))
    assert len(conversations) == 2 and budget.truncated
    assert client.streams_abandoned == 1


def test_browse_and_collect_release_the_reader_when_they_stop_early():
    # browse fills the requested page (2 matches > wanted=1) with the stream
    # suspended mid-page and must close it; collect hits scan_cap the same way.
    docs = [_stored('m0', 0), _stored('m1', 1)] + [
        _stored(f'n{i}', 2 + i, transcript_segments=_segments('other')) for i in range(58)
    ]
    client = _StrictClient(UID, docs)
    result = browse_conversations_by_speaker(
        iter_conversations(UID, limit=1000, batch=50, budget=_budget(), firestore_client=client),
        'p1',
        page=1,
        per_page=1,
    )
    assert len(result['items']) == 1
    assert client.raw_reads == 50  # one 50-row pull, never page 2
    assert client.streams_abandoned == 1

    client2 = _StrictClient(UID, [_stored(f'c{i}', i) for i in range(10)])
    stats = collect_people_stats(
        iter_conversations(UID, limit=10, batch=10, budget=_budget(), firestore_client=client2), scan_cap=2
    )
    assert stats['p1']['conversation_count'] == 2
    assert client2.streams_abandoned == 1


def test_unrelated_rpc_errors_propagate():
    def boom():
        raise RuntimeError('not a deadline')

    budget = _budget()
    client = _StrictClient(UID, [_stored('c0', 0), _stored('c1', 1)], tick=boom)
    with pytest.raises(RuntimeError):
        list(iter_conversations(UID, budget=budget, firestore_client=client))
    assert not budget.truncated


def test_scan_budget_is_required_and_limits_validated():
    with pytest.raises(TypeError):
        iter_conversations(UID, firestore_client=_StrictClient(UID, []))
    client = _StrictClient(UID, [])
    with pytest.raises(ValueError):
        list(iter_conversations(UID, limit=-1, budget=_budget(), firestore_client=client))
    with pytest.raises(ValueError):
        list(iter_conversations(UID, batch=0, budget=_budget(), firestore_client=client))


# ---------------------------------------------------------------------------
# Budget factory and projection fidelity
# ---------------------------------------------------------------------------


def test_scan_budget_consumes_the_middleware_start_stamp():
    # The middleware stamps request start before the handler runs; the budget
    # deadline must anchor there, not at handler time.
    request = SimpleNamespace(state=SimpleNamespace(**{REQUEST_STARTED_MONOTONIC_STATE_KEY: 50.0}))
    budget = conversation_scan_budget(request, route='people-stats')
    expected_seconds = min(conversation_scan.CONVERSATION_SCAN_SECONDS, resolve_list_read_budget_seconds())
    expected_documents = min(conversation_scan.CONVERSATION_SCAN_MAX_DOCUMENTS, resolve_list_read_max_documents())
    assert budget.max_documents == expected_documents
    assert budget._deadline == pytest.approx(50.0 + expected_seconds)


def test_scan_budget_defaults_without_a_request():
    budget = conversation_scan_budget(None, route='speaker-browse')
    assert budget.max_documents <= conversation_scan.CONVERSATION_SCAN_MAX_DOCUMENTS
    assert not budget.truncated


def test_scan_budget_env_can_lower_but_never_raise_the_ceilings(monkeypatch):
    # A high configured budget cannot exceed the scanner's own ceilings...
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '600')
    monkeypatch.setenv('OMI_LIST_READ_MAX_DOCUMENTS', '999999')
    budget = conversation_scan_budget(None, route='people-stats')
    assert budget.max_documents == conversation_scan.CONVERSATION_SCAN_MAX_DOCUMENTS
    assert budget.remaining_seconds <= conversation_scan.CONVERSATION_SCAN_SECONDS
    # ...while a low configured budget tightens the scan accordingly.
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '3')
    monkeypatch.setenv('OMI_LIST_READ_MAX_DOCUMENTS', '500')
    budget = conversation_scan_budget(None, route='people-stats')
    assert budget.max_documents == 500
    assert budget.remaining_seconds <= 3.0


def _encrypted_uncompressed(segments, uid: str) -> str:
    return encryption.encrypt(json.dumps(segments), uid)


def test_projected_scan_matches_full_reads_across_storage_shapes():
    """Stats over the PEOPLE_STATS_FIELD_PATHS projection equal stats over full reads.

    Covers standard compressed bytes, enhanced encrypted+compressed, enhanced
    legacy compressed bytes, uncompressed enhanced encrypted JSON, and legacy
    rows with no protection level in both compressed and plain form — all
    through the real codec helpers, no mocked decoding.
    """
    base = {'created_at': T0, 'discarded': False, 'is_locked': False}
    receipt = {'speakers': {'0': {'person_id': 'p2', 'is_user': False, 'generation': 1}}}

    # encode_conversation_for_write encodes the fields; the stored row's level
    # stamp is written by the route-layer decorator, so set it explicitly here.
    stored = [
        {
            **encode_conversation_for_write(
                UID,
                {**base, 'id': 'std', 'transcript_segments': _segments('p1', speaker_match_source='auto')},
                'standard',
            ),
            'data_protection_level': 'standard',
        },
        {
            **encode_conversation_for_write(
                UID,
                {**base, 'id': 'enh', 'transcript_segments': _segments('p1', speaker_match_source='auto')},
                'enhanced',
            ),
            'data_protection_level': 'enhanced',
        },
        # Enhanced legacy form: compressed bytes written before the level existed.
        {
            **base,
            'id': 'enh-legacy-compressed',
            'data_protection_level': 'enhanced',
            'transcript_segments': zlib.compress(
                json.dumps(_segments('p1', speaker_match_source='auto')).encode('utf-8')
            ),
            'transcript_segments_compressed': True,
        },
        # Missing-level row carrying compressed bytes decodes as standard.
        {
            **base,
            'id': 'no-level-compressed',
            'transcript_segments': zlib.compress(
                json.dumps(_segments('p3', speaker_match_source='auto')).encode('utf-8')
            ),
            'transcript_segments_compressed': True,
        },
        # Legacy row: no protection level, plain uncompressed segments.
        {**base, 'id': 'legacy', 'transcript_segments': _segments('p3')},
        # Enhanced row with the uncompressed (legacy) encrypted JSON form.
        {
            **base,
            'id': 'enh-plain',
            'data_protection_level': 'enhanced',
            'transcript_segments': _encrypted_uncompressed(_segments('p1', speaker_match_source='auto'), UID),
            'transcript_segments_compressed': False,
        },
        # Manual assignment receipt re-labels speaker 0 from p1 to p2.
        {
            **encode_conversation_for_write(
                UID,
                {
                    **base,
                    'id': 'receipted',
                    'transcript_segments': _segments('p1', speaker_match_source='auto'),
                    'manual_speaker_assignments': receipt,
                },
                'standard',
            ),
            'data_protection_level': 'standard',
        },
    ]

    expected = aggregate_people_stats([prepare_conversation_for_read(dict(doc), UID) for doc in stored])
    assert expected['p1']['conversation_count'] == 4  # std + enh + enh-legacy-compressed + enh-plain
    assert expected['p1']['talk_seconds'] == 8.0
    assert expected['p1']['auto_conversation_count'] == 4
    assert expected['p2']['conversation_count'] == 1  # receipt rewrote p1 -> p2
    assert expected['p2']['auto_conversation_count'] == 0  # receipt clears the auto marker
    assert expected['p3']['conversation_count'] == 2
    assert expected['p3']['talk_seconds'] == 4.0
    assert expected['p3']['auto_conversation_count'] == 1  # compressed auto + plain unmarked

    client, conversations = _scan(stored, field_paths=PEOPLE_STATS_FIELD_PATHS, limit=10, batch=2)
    actual = aggregate_people_stats(conversations)
    assert actual == expected

    # The receipt read: person_id rewrote and the automatic-match marker cleared.
    receipted = next(c for c in conversations if c['id'] == 'receipted')
    segment = receipted['transcript_segments'][0]
    assert segment['person_id'] == 'p2'
    assert segment['speaker_match_source'] is None


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_manual_receipt_overrides_under_every_protection_level(level):
    """The encrypted+compressed manual receipt decodes and re-labels under both levels."""
    base = {'created_at': T0, 'discarded': False, 'is_locked': False}
    receipt = {'speakers': {'0': {'person_id': 'p2', 'is_user': False, 'generation': 1}}}
    stored = [
        {
            **encode_conversation_for_write(
                UID,
                {
                    **base,
                    'id': 'receipted',
                    'transcript_segments': _segments('p1', speaker_match_source='auto'),
                    'manual_speaker_assignments': receipt,
                },
                level,
            ),
            'data_protection_level': level,
        },
    ]
    expected = aggregate_people_stats([prepare_conversation_for_read(dict(doc), UID) for doc in stored])
    _client, conversations = _scan(stored, field_paths=PEOPLE_STATS_FIELD_PATHS, limit=10, batch=1)
    actual = aggregate_people_stats(conversations)
    assert actual == expected
    assert actual['p2']['conversation_count'] == 1
    assert actual['p2']['talk_seconds'] == 2.0
    segment = conversations[0]['transcript_segments'][0]
    assert segment['person_id'] == 'p2' and segment['speaker_match_source'] is None


# ---------------------------------------------------------------------------
# Speaker browsing over the real reader
# ---------------------------------------------------------------------------


def _speaker_docs(n_newest: int, match_ids: List[str], person_id: str = 'p1') -> List[dict]:
    docs = [_stored(f'n{i}', i, transcript_segments=_segments('other')) for i in range(n_newest)]
    docs += [_stored(mid, n_newest + i, transcript_segments=_segments(person_id)) for i, mid in enumerate(match_ids)]
    return docs


def test_browse_pages_through_the_real_reader():
    docs = _speaker_docs(0, [f'm{i}' for i in range(25)])
    client = _StrictClient(UID, docs)
    results = [
        browse_conversations_by_speaker(
            iter_conversations(UID, limit=1000, batch=50, budget=_budget(), firestore_client=client),
            'p1',
            page=page,
            per_page=10,
        )
        for page in (1, 2, 3)
    ]
    for result in results:
        assert set(result.keys()) == {'items', 'total_pages', 'current_page', 'per_page'}
        assert result['per_page'] == 10
    assert [item['id'] for item in results[0]['items']] == [f'm{i}' for i in range(10)]
    assert [item['id'] for item in results[1]['items']] == [f'm{i}' for i in range(10, 20)]
    assert [item['id'] for item in results[2]['items']] == [f'm{i}' for i in range(20, 25)]
    assert [(r['total_pages'], r['current_page']) for r in results] == [(2, 1), (3, 2), (3, 3)]


@pytest.mark.parametrize('include_discarded', [False, True])
@pytest.mark.parametrize('with_date_window', [False, True])
def test_browse_honors_discarded_and_date_window_through_the_real_reader(include_discarded, with_date_window):
    """The actual browse function over the real reader honors both dimensions.

    Tombstones are invisible to the scan and locked rows are visible but
    filtered by browse; window bounds are inclusive at both edges.
    """
    docs = [
        _stored('too-new', 0),  # T0: after the window end
        _stored('edge-end', 1),  # T0-1: exactly the inclusive window end
        _stored('tomb', 50, deleted=True),  # inside the window, never yielded
        _stored('locked', 60, is_locked=True),  # inside, yielded, browse drops it
        _stored('disc', 100, discarded=True),  # inside, server-side filtered
        _stored('edge-start', 200),  # T0-200: exactly the inclusive window start
        _stored('too-old', 300),  # before the window start
    ]
    client = _StrictClient(UID, docs)
    window = (
        {'start_date': T0 - timedelta(seconds=200), 'end_date': T0 - timedelta(seconds=1)} if with_date_window else {}
    )
    result = browse_conversations_by_speaker(
        iter_conversations(
            UID,
            limit=1000,
            batch=10,
            include_discarded=include_discarded,
            budget=_budget(),
            firestore_client=client,
            **window,
        ),
        'p1',
        page=1,
        per_page=10,
        include_discarded=include_discarded,
    )
    expected = {
        (False, False): ['too-new', 'edge-end', 'edge-start', 'too-old'],
        (False, True): ['too-new', 'edge-end', 'disc', 'edge-start', 'too-old'],
        (True, False): ['edge-end', 'edge-start'],
        (True, True): ['edge-end', 'disc', 'edge-start'],
    }[(with_date_window, include_discarded)]
    assert [item['id'] for item in result['items']] == expected
    # The tombstone streams and is filtered in Python (counts as a raw read);
    # 'disc' is filtered server-side when include_discarded is False.
    assert (
        client.raw_reads
        == {(False, False): 6, (False, True): 7, (True, False): 4, (True, True): 5}[
            (with_date_window, include_discarded)
        ]
    )


def test_browse_date_window_bounds_are_inclusive():
    # start_date == end_date must still match the row stamped at that instant.
    docs = [_stored('edge', 5), _stored('outside', 6)]
    boundary = T0 - timedelta(seconds=5)
    _client, out = _scan(docs, limit=10, batch=10, start_date=boundary, end_date=boundary)
    assert [c['id'] for c in out] == ['edge']


def test_browse_preserves_full_item_payload():
    structured = {'title': 'generated', 'emoji': 'audio'}
    docs = [
        _stored(
            'full',
            0,
            structured=structured,
            user_title='My standup',
            finished_at=T0 + timedelta(seconds=5),
        )
    ]
    _client, conversations = _scan(docs, limit=10, batch=10)
    result = browse_conversations_by_speaker(iter(conversations), 'p1', page=1, per_page=10)
    assert set(result.keys()) == {'items', 'total_pages', 'current_page', 'per_page'}
    item = result['items'][0]
    # prepare_conversation_for_read merges the durable user title on top of the
    # generated structured title; the rest of the row ships verbatim.
    assert item['structured']['title'] == 'My standup'
    assert item['structured']['emoji'] == 'audio'
    assert item['finished_at'] == T0 + timedelta(seconds=5)
    assert item['transcript_segments'][0]['person_id'] == 'p1'


def test_browse_scan_cap_and_budget_truncation_both_report_more():
    docs = [_stored(f'c{i}', i, transcript_segments=_segments('other')) for i in range(50)]
    budget = _budget()
    client = _StrictClient(UID, docs)
    result = browse_conversations_by_speaker(
        iter_conversations(UID, limit=50, batch=50, budget=budget, firestore_client=client),
        'p1',
        page=1,
        per_page=10,
        scan_cap=50,
    )
    assert result['items'] == []
    assert result['total_pages'] == 2  # cap reached: the client may ask for more

    truncated_budget = _budget(max_documents=10)
    client2 = _StrictClient(UID, docs)
    result = browse_conversations_by_speaker(
        iter_conversations(UID, limit=50, batch=50, budget=truncated_budget, firestore_client=client2),
        'p1',
        page=1,
        per_page=10,
        scan_cap=50,
        budget=truncated_budget,
    )
    assert truncated_budget.truncated
    # Truncated with nothing to show: another page would repeat the same scan
    # and be empty again, so none is advertised.
    assert result['items'] == []
    assert result['total_pages'] == 1

    matching = [_stored(f'm{i}', i, transcript_segments=_segments('p1')) for i in range(50)]
    matching_budget = _budget(max_documents=10)
    result = browse_conversations_by_speaker(
        iter_conversations(
            UID, limit=50, batch=50, budget=matching_budget, firestore_client=_StrictClient(UID, matching)
        ),
        'p1',
        page=1,
        per_page=10,
        scan_cap=50,
        budget=matching_budget,
    )
    assert matching_budget.truncated
    assert len(result['items']) == 10
    assert result['total_pages'] == 2  # truncated with rows shown: more may exist


# ---------------------------------------------------------------------------
# Route-level wiring: people stats and speaker browse under TestClient
# ---------------------------------------------------------------------------


def _people_client(monkeypatch, docs, *, people=None, tick=None, budget=None):
    monkeypatch.setattr(
        users_router,
        'get_people',
        lambda uid: people if people is not None else [{'id': 'p1', 'name': 'Ann'}],
    )
    client = _StrictClient('test-uid', docs, tick=tick)
    monkeypatch.setattr(conversation_scan, 'get_firestore_client', lambda: client)
    if budget is not None:
        monkeypatch.setattr(users_router, 'conversation_scan_budget', lambda *a, **k: budget)
    app = FastAPI()
    app.include_router(users_router.router)
    app.dependency_overrides[users_router.auth.get_current_user_uid] = lambda: 'test-uid'
    return TestClient(app, raise_server_exceptions=False), client


def test_people_route_returns_stats(monkeypatch):
    http, client = _people_client(monkeypatch, [_stored('c0', 0)])
    resp = http.get('/v1/users/people', params={'include_stats': 'true', 'include_speech_samples': 'false'})
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]['conversation_count'] == 1
    assert body[0]['talk_seconds'] == 2.0
    assert OMI_LIST_TRUNCATED_HEADER not in resp.headers
    assert client.queries and all(q['limit'] for q in client.queries)


def test_people_route_marks_truncated_when_document_budget_runs_out(monkeypatch):
    monkeypatch.setenv('OMI_LIST_READ_MAX_DOCUMENTS', '1')
    http, client = _people_client(monkeypatch, [_stored(f'c{i}', i) for i in range(5)])
    resp = http.get('/v1/users/people', params={'include_stats': 'true', 'include_speech_samples': 'false'})
    assert resp.status_code == 200
    assert resp.headers[OMI_LIST_TRUNCATED_HEADER] == 'true'
    # The partial stats still shipped.
    assert resp.json()[0]['conversation_count'] == 1


def test_people_route_marks_truncated_when_the_deadline_passes(monkeypatch):
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '0')
    http, _client_fake = _people_client(monkeypatch, [_stored('c0', 0)])
    resp = http.get('/v1/users/people', params={'include_stats': 'true', 'include_speech_samples': 'false'})
    assert resp.status_code == 200
    assert resp.headers[OMI_LIST_TRUNCATED_HEADER] == 'true'
    assert resp.json()[0]['conversation_count'] == 0


def test_people_route_scans_past_tombstones_to_the_raw_budget(monkeypatch):
    # Default stats scan against >2,000 raw rows (mostly deleted): reads
    # exactly the 2,000-document ceiling, ships the honest prefix, header set.
    monkeypatch.delenv('OMI_LIST_READ_MAX_DOCUMENTS', raising=False)
    monkeypatch.delenv('OMI_LIST_READ_BUDGET_SECONDS', raising=False)
    docs = [_stored('v0', 0)] + [_stored(f'd{i}', 1 + i, deleted=True) for i in range(2000)] + [_stored('v1', 2001)]
    http, client = _people_client(monkeypatch, docs)
    resp = http.get('/v1/users/people', params={'include_stats': 'true', 'include_speech_samples': 'false'})
    assert resp.status_code == 200
    assert client.raw_reads == 2000
    assert resp.headers[OMI_LIST_TRUNCATED_HEADER] == 'true'
    assert resp.json()[0]['conversation_count'] == 1


def test_people_route_returns_the_prefix_when_the_deadline_hits_mid_scan(monkeypatch):
    # Each streamed row costs 5s on the injected clock; the 12s deadline lands
    # on the third row, so the route ships the two-row prefix with truncation.
    clock_now = [1000.0]
    budget = ListReadBudget(
        deadline_monotonic=1012.0,
        max_documents=2000,
        clock=lambda: clock_now[0],
        started_monotonic=1000.0,
    )
    docs = [_stored(f'c{i}', i) for i in range(5)]
    http, _client = _people_client(
        monkeypatch, docs, tick=lambda: clock_now.__setitem__(0, clock_now[0] + 5.0), budget=budget
    )
    resp = http.get('/v1/users/people', params={'include_stats': 'true', 'include_speech_samples': 'false'})
    assert resp.status_code == 200
    assert resp.headers[OMI_LIST_TRUNCATED_HEADER] == 'true'
    assert budget.exhaustion_reason == 'deadline'
    assert resp.json()[0]['conversation_count'] == 2


def _speaker_client(monkeypatch, docs, budget=None):
    client = _StrictClient('test-uid', docs)
    monkeypatch.setattr(
        conversations_router.conversation_scan_db,
        'speaker_browse_scan',
        lambda uid, **kwargs: iter_conversations(
            uid,
            limit=conversation_scan.SPEAKER_BROWSE_SCAN_CAP,
            batch=conversation_scan.SPEAKER_BROWSE_BATCH,
            firestore_client=client,
            **kwargs,
        ),
    )
    if budget is not None:
        monkeypatch.setattr(
            conversations_router.conversation_scan_db, 'conversation_scan_budget', lambda request, route: budget
        )
    monkeypatch.setattr(conversations_router.users_db, 'get_person', lambda uid, pid: {'id': pid})
    monkeypatch.setattr(auth_endpoints, 'check_rate_limit', lambda *a, **k: (True, 9, 0))
    app = FastAPI()
    app.include_router(conversations_router.router)
    app.dependency_overrides[auth_endpoints.get_current_user_uid] = lambda: 'test-uid'
    return TestClient(app, raise_server_exceptions=False), client


def test_speaker_browse_route_walks_past_the_latest_page(monkeypatch):
    docs = _speaker_docs(60, ['old-1'], person_id='person-1')
    http, client = _speaker_client(monkeypatch, docs)
    resp = http.post('/v1/conversations/search', json={'query': '', 'speaker_id': 'person-1', 'per_page': 20})
    assert resp.status_code == 200
    assert [item['id'] for item in resp.json()['items']] == ['old-1']
    assert client.raw_reads == 61


def test_speaker_browse_route_sets_truncated_header_on_budget_exhaustion(monkeypatch):
    docs = _speaker_docs(30, [])
    budget = _budget(max_documents=10)
    http, client = _speaker_client(monkeypatch, docs, budget=budget)
    resp = http.post('/v1/conversations/search', json={'query': '', 'speaker_id': 'person-1', 'per_page': 10})
    assert resp.status_code == 200
    assert resp.headers[OMI_LIST_TRUNCATED_HEADER] == 'true'
    assert budget.exhaustion_reason == 'documents'
