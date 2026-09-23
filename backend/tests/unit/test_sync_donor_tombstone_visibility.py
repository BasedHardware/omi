"""Donor redirect tombstones must not surface on conversation read paths.

PR #15193 writes `deleted=True` + `sync_merged_into` on absorbed sync donors but
leaves `discarded` untouched. User-facing list/count readers only filter
`discarded == False`, so the fragments stay on screen. A late chunk that still
names the donor id must follow `sync_merged_into` to the survivor.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from google.cloud import firestore

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_capture_continuity import capture
from tests.unit.test_sync_cross_job_assignment import intake
from utils.other.list_budget import ListReadBudget


class _ListingDoc:
    def __init__(self, document_id: str, data: dict[str, Any]):
        self.id = document_id
        self._data = dict(data)
        self._data.setdefault('id', document_id)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class _ListingQuery:
    def __init__(
        self,
        docs: list[_ListingDoc],
        *,
        filters: list[Any] | None = None,
        order_field: str | None = None,
        descending: bool = False,
        offset: int = 0,
        limit: int | None = None,
        start_after_id: str | None = None,
    ):
        self._docs = docs
        self._filters = list(filters or [])
        self._order_field = order_field
        self._descending = descending
        self._offset = offset
        self._limit = limit
        self._start_after_id = start_after_id

    def where(self, *args: Any, **kwargs: Any) -> '_ListingQuery':
        filt = kwargs.get('filter') or (args[0] if args else None)
        return self._copy(filters=self._filters + [filt])

    def order_by(self, field: str, direction: Any = None) -> '_ListingQuery':
        return self._copy(order_field=field, descending=direction == firestore.Query.DESCENDING)

    def offset(self, value: int) -> '_ListingQuery':
        return self._copy(offset=value)

    def limit(self, value: int) -> '_ListingQuery':
        return self._copy(limit=value)

    def start_after(self, snapshot: _ListingDoc) -> '_ListingQuery':
        return self._copy(start_after_id=snapshot.id)

    def count(self) -> SimpleNamespace:
        n = len(self._matching())
        return SimpleNamespace(get=lambda: [[SimpleNamespace(value=n)]])

    def stream(self, **_kwargs: Any):
        docs = self._matching()
        if self._start_after_id is not None:
            start = next(index for index, doc in enumerate(docs) if doc.id == self._start_after_id) + 1
            docs = docs[start:]
        docs = docs[self._offset :]
        if self._limit is not None:
            docs = docs[: self._limit]
        return iter(docs)

    def _copy(self, **overrides: Any) -> '_ListingQuery':
        params: dict[str, Any] = {
            'filters': self._filters,
            'order_field': self._order_field,
            'descending': self._descending,
            'offset': self._offset,
            'limit': self._limit,
            'start_after_id': self._start_after_id,
        }
        params.update(overrides)
        return _ListingQuery(self._docs, **params)

    def _matching(self) -> list[_ListingDoc]:
        docs = list(self._docs)
        for filt in self._filters:
            if filt is None:
                continue
            field = getattr(filt, 'field_path', None)
            op = getattr(filt, 'op_string', '==')
            value = getattr(filt, 'value', None)
            docs = [doc for doc in docs if _matches(doc._data, field, op, value)]
        if self._order_field:
            docs.sort(key=lambda doc: doc._data.get(self._order_field), reverse=self._descending)
        return docs


class _ListingCollection:
    def __init__(self, docs: list[_ListingDoc]):
        self._query = _ListingQuery(docs)

    def where(self, *args: Any, **kwargs: Any) -> _ListingQuery:
        return self._query.where(*args, **kwargs)

    def order_by(self, *args: Any, **kwargs: Any) -> _ListingQuery:
        return self._query.order_by(*args, **kwargs)

    def offset(self, value: int) -> _ListingQuery:
        return self._query.offset(value)

    def limit(self, value: int) -> _ListingQuery:
        return self._query.limit(value)

    def count(self) -> SimpleNamespace:
        return self._query.count()

    def stream(self, **kwargs: Any) -> list[_ListingDoc]:
        return self._query.stream(**kwargs)


class _ListingDb:
    def __init__(self, rows: dict[str, dict[str, Any]]):
        self._docs = [_ListingDoc(doc_id, data) for doc_id, data in rows.items()]

    def collection(self, name: str) -> '_ListingDb':
        assert name == 'users'
        return self

    def document(self, _uid: str) -> SimpleNamespace:
        return SimpleNamespace(collection=lambda _name: _ListingCollection(self._docs))


def _matches(data: dict[str, Any], field: str | None, op: str, value: Any) -> bool:
    if not field:
        return True
    if field not in data:
        return False
    actual = data[field]
    if op == '==':
        return actual == value
    if op == 'in':
        return actual in value
    if op == '>=':
        return actual >= value
    if op == '<=':
        return actual <= value
    raise AssertionError(f'unsupported listing filter {field} {op}')


def _rows_from_store(store: StrictFirestore) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for key, value in store.rows.items():
        if len(key) != 4 or key[2] != 'conversations':
            continue
        row = deepcopy(value)
        row.setdefault('id', key[3])
        row.setdefault('created_at', row.get('started_at'))
        row.setdefault('status', 'completed')
        row.setdefault('data_protection_level', 'standard')
        rows[str(key[3])] = row
    return rows


def _merge_pair() -> tuple[StrictFirestore, str, str]:
    """Bridge two already-persisted captures so assignment writes a donor tombstone.

    Adjacent incoming chunk IDs append in place. A genuine bridge needs two
    existing rows later joined by a spanning chunk, which is the #15193 shape.
    """
    store = StrictFirestore()
    left, _, _ = intake(store, capture(0))
    right, _, _ = intake(store, capture(4))
    assert left['id'] != right['id']
    bridged, _, _ = intake(store, capture(2))
    survivor_id = bridged['id']
    donor_id = next(
        key[3]
        for key, value in store.rows.items()
        if len(key) == 4 and key[2] == 'conversations' and value.get('deleted')
    )
    assert donor_id != survivor_id
    assert store.rows[('users', 'u', 'conversations', donor_id)]['sync_merged_into'] == survivor_id
    assert store.rows[('users', 'u', 'conversations', donor_id)]['discarded'] is True
    return store, survivor_id, donor_id


def _install_listing(monkeypatch: pytest.MonkeyPatch, rows: dict[str, dict[str, Any]]) -> None:
    from database import conversations as conversations_db

    monkeypatch.setattr(conversations_db, 'db', _ListingDb(rows))
    monkeypatch.setattr(conversations_db, '_document_data_with_revision', lambda doc: doc.to_dict())


@pytest.fixture(scope='module', autouse=True)
def dependencies() -> None:
    from database import conversations  # noqa: F401


def test_donor_tombstone_is_absent_from_default_list_and_count(monkeypatch: pytest.MonkeyPatch) -> None:
    from database import conversations as conversations_db

    store, survivor_id, donor_id = _merge_pair()
    _install_listing(monkeypatch, _rows_from_store(store))

    listed = conversations_db.get_conversations_without_photos('u', limit=20, offset=0, include_discarded=True)
    listed_kept = conversations_db.get_conversations_without_photos('u', limit=20, offset=0, include_discarded=False)
    ids = {row['id'] for row in listed}
    kept_ids = {row['id'] for row in listed_kept}

    assert survivor_id in ids
    assert donor_id not in ids
    assert donor_id not in kept_ids
    assert conversations_db.get_conversations_count('u', include_discarded=False) == 1
    assert conversations_db.get_conversations_count('u', include_discarded=True) == 1


def test_include_discarded_page_fills_visible_rows_around_a_donor(monkeypatch: pytest.MonkeyPatch) -> None:
    from database import conversations as conversations_db

    store, survivor_id, donor_id = _merge_pair()
    rows = _rows_from_store(store)
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows['visible-old'] = {
        'id': 'visible-old',
        'created_at': older,
        'started_at': older,
        'discarded': False,
        'deleted': False,
        'status': 'completed',
        'data_protection_level': 'standard',
    }
    _install_listing(monkeypatch, rows)

    page = conversations_db.get_conversations_without_photos('u', limit=2, offset=0, include_discarded=True)
    page_ids = [row['id'] for row in page]
    assert donor_id not in page_ids
    assert len(page_ids) == 2
    assert survivor_id in page_ids

    rest = conversations_db.get_conversations_without_photos('u', limit=2, offset=2, include_discarded=True)
    rest_ids = [row['id'] for row in rest]
    assert donor_id not in rest_ids
    assert page_ids + rest_ids == [survivor_id, 'visible-old'] or set(page_ids + rest_ids) == {
        survivor_id,
        'visible-old',
    }


def test_user_discarded_row_stays_visible_when_include_discarded(monkeypatch: pytest.MonkeyPatch) -> None:
    from database import conversations as conversations_db

    created = datetime(2026, 3, 1, tzinfo=timezone.utc)
    rows = {
        'kept': {
            'id': 'kept',
            'created_at': created,
            'discarded': False,
            'status': 'completed',
        },
        'user-discarded': {
            'id': 'user-discarded',
            'created_at': created,
            'discarded': True,
            'status': 'completed',
        },
        'donor': {
            'id': 'donor',
            'created_at': created,
            'discarded': True,
            'deleted': True,
            'sync_merged_into': 'kept',
            'status': 'completed',
        },
    }
    _install_listing(monkeypatch, rows)

    included = {row['id'] for row in conversations_db.get_conversations_without_photos('u', include_discarded=True)}
    excluded = {row['id'] for row in conversations_db.get_conversations_without_photos('u', include_discarded=False)}
    assert included == {'kept', 'user-discarded'}
    assert excluded == {'kept'}
    assert conversations_db.get_conversations_count('u', include_discarded=True) == 2
    assert conversations_db.get_conversations_count('u', include_discarded=False) == 1


def test_donor_id_still_redirects_late_sync_chunks() -> None:
    store, survivor_id, donor_id = _merge_pair()
    late = capture(3)
    late['id'] = donor_id
    result, created, _survivors = intake(store, late)
    assert not created
    assert result['id'] == survivor_id
    hinted = capture(3)
    hinted['id'] = 'late-hint'
    result, created, _ = intake(store, hinted, target_id=donor_id)
    assert result['id'] == survivor_id
    assert not created
    assert store.rows[('users', 'u', 'conversations', donor_id)]['sync_merged_into'] == survivor_id


def test_budgeted_include_discarded_page_does_not_count_donor_against_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from database import conversations as conversations_db

    store, survivor_id, donor_id = _merge_pair()
    _install_listing(monkeypatch, _rows_from_store(store))
    budget = ListReadBudget(
        deadline_monotonic=1_000_000.0,
        max_documents=25_000,
        route='conversations',
        clock=lambda: 0.0,
        started_monotonic=0.0,
    )
    page = conversations_db.get_conversations_without_photos(
        'u', limit=1, offset=0, include_discarded=True, budget=budget
    )
    assert [row['id'] for row in page] == [survivor_id]
    assert donor_id not in {row['id'] for row in page}
    assert not budget.truncated
