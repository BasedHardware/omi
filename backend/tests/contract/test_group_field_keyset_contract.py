"""Dual-backend contract for the collection-group FIELD keyset (ADR-0002 port, BACKLOG L39).

A collection-group scan could only page one way: by document path, in the implicit document-name order.
That is right for a full pass and useless for an incremental one, because a range filter forces the
ordering onto the filtered field — and both adapters refused a name cursor combined with an `order_by`
rather than build an invalid one. So "everything matching a range, in that range's order, resumable"
was not expressible over a collection group at all.

**What this does NOT enable, measured rather than assumed.** It was written to let the conversation
search reconciler read only what changed instead of every conversation every five minutes. It cannot:
`updated_at` on a conversation is not a payload field but the STORE's revision, injected into the dict
on read and explicitly popped before every write ("never an application-owned field to replay into a
later write", database/conversations.py, three sites). So there is nothing persisted to range over, and
the incremental scan would find nothing, forever — confirmed on the live stack, where a pass that
indexed four conversations came back with no high-water mark at all. Making it possible means persisting
the revision as a field, which is a storage-format change with a migration and contradicts a deliberate
rule; that is a decision, not a follow-up (BACKLOG L39).

The cursor stands on its own regardless: it is the missing form, the adapters were already refusing the
wrong pairing on purpose, and any range-ordered group scan needs it.

    cursor    `start_after={"value": <order-field value>, "id": <full path>}` positions an explicit
              order. The failure mode is the one every cursor shares and the reason these tests assert
              DISTINCTNESS rather than page length: a cursor the backend mishandles either repeats a
              page forever — which reads as progress and never terminates — or steps over rows, which
              is silent and permanent.

Two properties beyond paging, both of which a naive implementation gets wrong:

  * TIES. Several documents can carry the same timestamp — a batch write gives them all one. A cursor
    on the value alone either loses every tied row after the first page or serves them twice. The path
    is the tiebreak, and the keyset has to be a disjunction: past the value, OR equal to it and past
    the path.
  * ROWS MISSING THE FIELD. Firestore's order excludes a document that lacks the ordered field. Mongo
    would sort it first (null). The port matches Firestore, so an incremental scan cannot see a legacy
    row that has no timestamp — which is not a bug to fix here but a fact a caller must plan for, and
    is pinned below so nobody discovers it in production.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

BASE = datetime(2026, 8, 1, tzinfo=timezone.utc)
GROUP = 'keyset_probe'


@pytest.fixture
def rows(bind_store):
    """Six documents across two parents, with a deliberate tie in the middle."""
    run = uuid.uuid4().hex[:8]
    paths: list[str] = []

    def seed(parent: str, name: str, day: int) -> str:
        path = f'users/kx{parent}-{run}/{GROUP}/{name}-{run}'
        bind_store.set(path, {'id': name, 'changed_at': BASE + timedelta(days=day)})
        paths.append(path)
        return path

    for index, (parent, name, day) in enumerate(
        [('a', 'r0', 0), ('a', 'r1', 1), ('a', 'r2', 2), ('b', 'r3', 2), ('b', 'r4', 3), ('b', 'r5', 4)]
    ):
        seed(parent, name, day)

    yield {'store': bind_store, 'run': run, 'paths': paths}

    for path in paths:
        bind_store.delete(path)


def _page(rows, *, after=None, limit=2, cutoff=BASE):
    return rows['store'].query_group(
        GROUP,
        filters=[('changed_at', '>=', cutoff)],
        order_by='changed_at',
        limit=limit,
        start_after=after,
    )


def _cursor(record):
    return {'value': record.data['changed_at'], 'id': record.path}


def _walk(rows, *, limit=2, cutoff=BASE):
    """Page to exhaustion, bounded — the bound is itself an assertion.

    An unbounded loop is what a non-advancing cursor turns into, and then the test hangs instead of
    reporting. Ten pages of two is comfortably past six rows.
    """
    seen: list = []
    cursor = None
    for _ in range(10):
        page = _page(rows, after=cursor, limit=limit, cutoff=cutoff)
        if not page:
            return seen
        seen.extend(page)
        cursor = _cursor(page[-1])
    pytest.fail('the scan did not terminate — the cursor is not advancing')


def test_the_scan_pages_without_repeating_or_skipping(rows):
    walked = _walk(rows)

    assert len(walked) == 6, f'expected every row exactly once, walked {len(walked)}'
    assert len({record.path for record in walked}) == 6, 'a later page repeated a row'


def test_the_pages_come_back_in_change_order(rows):
    walked = _walk(rows)

    stamps = [record.data['changed_at'] for record in walked]
    assert stamps == sorted(stamps), 'an incremental scan that is not ordered by the change cannot resume'


def test_rows_sharing_a_timestamp_are_each_served_once(rows):
    """The tie is deliberate: two rows on day 2, under different parents. A cursor on the value alone
    either drops the second or serves it forever."""
    walked = _walk(rows, limit=1)

    tied = [record.data['id'] for record in walked if record.data['changed_at'] == BASE + timedelta(days=2)]
    assert sorted(tied) == ['r2', 'r3'], f'the tied rows were not each served exactly once: {tied}'


def test_the_cutoff_excludes_what_did_not_change(rows):
    walked = _walk(rows, cutoff=BASE + timedelta(days=3))

    assert sorted(record.data['id'] for record in walked) == ['r4', 'r5']


def test_the_scan_crosses_parents(rows):
    """It is a collection GROUP scan: the point is that one pass covers every user."""
    walked = _walk(rows)

    parents = {record.path.split('/')[1] for record in walked}
    assert len(parents) == 2


def test_a_row_with_no_timestamp_is_not_served_by_an_incremental_scan(rows):
    """Pinned, not fixed. Firestore's order excludes a document missing the ordered field and the port
    matches that, so a legacy row with no `changed_at` is invisible to a changed-since pass. A caller
    that needs those rows needs a full pass — which is exactly why the reconciler keeps one."""
    orphan = f"users/kxa-{rows['run']}/{GROUP}/legacy-{rows['run']}"
    rows['store'].set(orphan, {'id': 'legacy'})
    rows['paths'].append(orphan)

    walked = _walk(rows)

    assert 'legacy' not in {record.data.get('id') for record in walked}
    assert len(rows['store'].query_group(GROUP, filters=[('__name__', '==', orphan)])) == 1, 'but it IS there'


def test_a_field_keyset_without_an_order_is_refused(rows):
    """Rather than building a cursor that positions nothing. Both adapters and the fake agree."""
    with pytest.raises(NotImplementedError):
        rows['store'].query_group(GROUP, start_after={'value': BASE, 'id': rows['paths'][0]})


def test_the_document_path_keyset_still_pages_a_full_scan(rows):
    """The other cursor form must keep working: the full pass the reconciler uses for pruning depends on
    it, and it is the one that does NOT need every row to carry a timestamp."""
    first = rows['store'].query_group(GROUP, limit=4)
    second = rows['store'].query_group(GROUP, limit=4, start_after=first[-1].path)

    assert len(first) == 4
    assert {record.path for record in first} & {record.path for record in second} == set()
