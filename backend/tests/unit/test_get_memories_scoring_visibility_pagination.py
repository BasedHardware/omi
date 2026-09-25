"""get_memories scoring_desc must fill `limit` with *visible* rows.

Firestore applies limit/offset before Python drops user-rejected
(``user_review is False``) and invalidated (``invalid_at`` set) rows. A hidden
row in the middle of a raw page therefore returns a short visible page and
leaves later visible memories unfetched — callers that stop after one page
(or treat len < limit as EOF) never see them.

Same failure class as chat ``get_messages`` reported pagination: raw page
limit before the visibility filter. This pins it against a fake that mirrors
Firestore offset+limit (broken) and start_after scan (fixed) semantics.
"""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import database.memories as memories_db


class _FakeDoc:
    def __init__(self, data: Dict[str, Any]):
        self.id = data['id']
        self._data = dict(data)

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(
        self,
        docs: List[_FakeDoc],
        *,
        filters: Optional[List] = None,
        requested_offset: int = 0,
        requested_limit: Optional[int] = None,
        batches: Optional[List[int]] = None,
    ):
        self._docs = docs
        self._filters = list(filters or [])
        self.requested_offset = requested_offset
        self.requested_limit = requested_limit
        # Shared across derived queries: one entry per raw Firestore read, so a test
        # can see how many documents the scan actually streamed and in how many batches.
        self.batches = batches if batches is not None else []

    def where(self, *args, **kwargs):
        filt = kwargs.get('filter') or (args[0] if args else None)
        return _FakeQuery(
            self._docs,
            filters=self._filters + [filt],
            requested_offset=self.requested_offset,
            requested_limit=self.requested_limit,
            batches=self.batches,
        )

    def order_by(self, *args, **kwargs):
        return self

    def select(self, fields):
        return self

    def offset(self, value: int):
        return _FakeQuery(
            self._docs,
            filters=self._filters,
            requested_offset=value,
            requested_limit=self.requested_limit,
            batches=self.batches,
        )

    def limit(self, value: int):
        return _FakeQuery(
            self._docs,
            filters=self._filters,
            requested_offset=self.requested_offset,
            requested_limit=value,
            batches=self.batches,
        )

    def start_after(self, document):
        start = next(i for i, row in enumerate(self._docs) if row.id == document.id) + 1
        return _FakeQuery(
            self._docs,
            filters=self._filters,
            requested_offset=start,
            requested_limit=self.requested_limit,
            batches=self.batches,
        )

    def stream(self):
        rows = self._docs
        start = self.requested_offset
        end = start + (self.requested_limit if self.requested_limit is not None else len(rows))
        page = rows[start:end]
        self.batches.append(len(page))
        for doc in page:
            yield _FakeDoc({'id': doc.id, **doc._data})


class _FakeDB:
    def __init__(self, docs: List[_FakeDoc]):
        self._docs = docs
        self.batches: List[int] = []

    def collection(self, _name: str):
        return self

    def document(self, _uid: str):
        return SimpleNamespace(collection=self._user_collection)

    def _user_collection(self, _name: str):
        return _FakeQuery(self._docs, batches=self.batches)


def _memory_row(memory_id: str, **fields: Any) -> Dict[str, Any]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = {
        'id': memory_id,
        'content': memory_id,
        'category': 'interesting',
        'created_at': now,
        'updated_at': now,
        'scoring': 1.0,
    }
    row.update(fields)
    return row


def _call_scoring_page(docs: List[_FakeDoc], *, limit: int, offset: int = 0, db_out: Optional[List] = None):
    # No decrypt stub here: @prepare_for_read binds _prepare_memory_for_read into its
    # wrapper closure at decoration time, so patching the module attribute would do
    # nothing. These rows carry no data_protection_level='enhanced', so the real read
    # path is a pass-through and the fixtures exercise it unmodified.
    fake_db = _FakeDB(docs)
    if db_out is not None:
        db_out.append(fake_db)
    return memories_db.get_memories(
        'uid-scoring-vis',
        limit=limit,
        offset=offset,
        sort='scoring_desc',
        firestore_client=fake_db,
    )


def test_rejected_row_in_middle_of_page_does_not_shorten_visible_limit():
    """user_review=False in the raw page must not steal a visible slot.

    Scoring stream: visible-a, rejected, visible-b, visible-c.
    limit=2 must return [visible-a, visible-b], not a short [visible-a] that
    leaves visible-b unfetched for single-page / len<limit EOF callers.
    """
    docs = [
        _FakeDoc(_memory_row('visible-a')),
        _FakeDoc(_memory_row('rejected', user_review=False)),
        _FakeDoc(_memory_row('visible-b')),
        _FakeDoc(_memory_row('visible-c')),
    ]
    page = _call_scoring_page(docs, limit=2, offset=0)
    assert [row['id'] for row in page] == ['visible-a', 'visible-b']


def test_invalidated_row_in_middle_of_page_does_not_shorten_visible_limit():
    """invalid_at in the raw page must not steal a visible slot either."""
    docs = [
        _FakeDoc(_memory_row('visible-a')),
        _FakeDoc(_memory_row('gone', invalid_at=datetime(2026, 1, 2, tzinfo=timezone.utc))),
        _FakeDoc(_memory_row('visible-b')),
    ]
    page = _call_scoring_page(docs, limit=2, offset=0)
    assert [row['id'] for row in page] == ['visible-a', 'visible-b']


def test_offset_advances_by_visible_rows_not_raw_firestore_slots():
    """Page-2 offset must skip visible rows only, matching what page 1 returned.

    After a full visible page of 2, offset=2 must continue at visible-c — not
    jump past it because rejected/invalid rows inflated the raw Firestore offset.
    """
    docs = [
        _FakeDoc(_memory_row('visible-a')),
        _FakeDoc(_memory_row('rejected-1', user_review=False)),
        _FakeDoc(_memory_row('visible-b')),
        _FakeDoc(_memory_row('gone', invalid_at=datetime(2026, 1, 2, tzinfo=timezone.utc))),
        _FakeDoc(_memory_row('visible-c')),
        _FakeDoc(_memory_row('visible-d')),
    ]
    first = _call_scoring_page(docs, limit=2, offset=0)
    second = _call_scoring_page(docs, limit=2, offset=2)
    assert [row['id'] for row in first] == ['visible-a', 'visible-b']
    assert [row['id'] for row in second] == ['visible-c', 'visible-d']


def test_scan_continues_across_batches_through_a_dense_block_of_hidden_rows():
    """The cursor continuation is the fix, so a page must be filled across batches.

    Every earlier fixture fits in one batch, so the loop exited after the first read
    and start_after was never called -- the mechanism was untested. Here 150 rejected
    rows sit ahead of the visible ones, which exceeds the 100-document batch ceiling
    and forces the scan to resume from the cursor.
    """
    docs = [_FakeDoc(_memory_row(f'rejected-{i}', user_review=False)) for i in range(150)]
    docs += [_FakeDoc(_memory_row('visible-a')), _FakeDoc(_memory_row('visible-b'))]

    seen: List[Any] = []
    page = _call_scoring_page(docs, limit=2, offset=0, db_out=seen)

    assert [row['id'] for row in page] == ['visible-a', 'visible-b']
    assert len(seen[0].batches) > 1, 'the page must have required more than one raw read'


def test_a_clean_page_streams_no_more_documents_than_it_returns():
    """Nothing hidden means no slack: the read costs exactly what the page needs.

    The first version floored the budget at 100 and read a flat 100-document first
    batch, so every small page streamed 100 full documents on an endpoint with a
    documented 504 history (#11831).
    """
    docs = [_FakeDoc(_memory_row(f'visible-{i}')) for i in range(500)]

    seen: List[Any] = []
    page = _call_scoring_page(docs, limit=5, offset=0, db_out=seen)

    assert [row['id'] for row in page] == [f'visible-{i}' for i in range(5)]
    assert sum(seen[0].batches) == 5


def test_a_deep_offset_is_still_serviced_rather_than_reported_as_end_of_data():
    """A deep offset must return its page, not a short one callers read as EOF.

    Capping the *total* scan at 2000 meant offset + limit past the cap could never be
    reached, so the page came back empty -- the same "later visible rows are never
    fetched" defect this scan exists to fix, reintroduced at depth, and a regression
    against the raw .offset() it replaced.
    """
    docs = [_FakeDoc(_memory_row(f'visible-{i}')) for i in range(2300)]

    page = _call_scoring_page(docs, limit=5, offset=2200)

    assert [row['id'] for row in page] == [f'visible-{i}' for i in range(2200, 2205)]


def test_slack_stays_bounded_when_every_scanned_row_is_hidden():
    """Flooring the budget at the page must not become an unbounded stream."""
    docs = [_FakeDoc(_memory_row(f'rejected-{i}', user_review=False)) for i in range(9000)]

    seen: List[Any] = []
    page = _call_scoring_page(docs, limit=10, offset=0, db_out=seen)

    assert page == []
    assert sum(seen[0].batches) <= 10 + memories_db._MEMORY_SCORING_VISIBLE_PAGE_SCAN_SLACK


def test_a_page_that_dies_on_the_budget_says_so(caplog):
    """A budget-exhausted page must be distinguishable from end-of-data in the logs.

    This is the one edge a bounded scan cannot design away: when the ceiling stops the
    scan mid-hidden-run, the caller receives a short page and cannot tell it apart from
    having reached the end of the collection. The log line is the only signal that the
    slack was too small for this account, so it has to fire here -- and nowhere else.
    """
    docs = [_FakeDoc(_memory_row(f'rejected-{i}', user_review=False)) for i in range(9000)]

    with caplog.at_level(logging.WARNING, logger=memories_db.logger.name):
        page = _call_scoring_page(docs, limit=10, offset=0)

    assert page == []
    assert 'get_memories_scan_budget_exhausted' in caplog.text
    assert f'budget={10 + memories_db._MEMORY_SCORING_VISIBLE_PAGE_SCAN_SLACK}' in caplog.text


def test_a_page_that_simply_ran_out_of_rows_stays_quiet(caplog):
    """The dangerous direction: warning on every short page would make the signal useless.

    A collection with fewer rows than the page asks for is ordinary end-of-data, not a
    budget failure, and must not be reported as one.
    """
    docs = [_FakeDoc(_memory_row(f'visible-{i}')) for i in range(3)]

    with caplog.at_level(logging.WARNING, logger=memories_db.logger.name):
        page = _call_scoring_page(docs, limit=10, offset=0)

    assert len(page) == 3, 'precondition: a genuinely short page'
    assert 'get_memories_scan_budget_exhausted' not in caplog.text
