"""get_scores overall totals must come from count() aggregation, not by materializing the whole
action_items collection (unbounded memory/latency for large accounts).

The overall bucket previously streamed every document into process just to count it. The fix uses
store.count() with a deleted-subset subtraction (mirroring get_action_items_count_by_conversation).
This test asserts the counts stay correct AND that no unbounded, unfiltered scan of the collection
is issued for the overall bucket. Exercised through the ADR-0044 facade seam
(install_fake_db_client): db.collection().count() lands on store.count(), db...stream() on
store.query(), so a recording fake proves the overall bucket never issues an unfiltered query().
"""

from database import action_items as action_items_db
from tests.store_fakes import FakeDocumentStore, install_fake_db_client

_UID = 'uid'
_PATH = f'users/{_UID}/action_items'


class _RecordingStore(FakeDocumentStore):
    def __init__(self):
        super().__init__()
        self.query_calls = []

    def query(self, collection, *, filters=None, **kwargs):
        self.query_calls.append((collection, list(filters or [])))
        return super().query(collection, filters=filters, **kwargs)


def _seed(store, item_id, **fields):
    store._docs[f'{_PATH}/{item_id}'] = dict(fields)


def test_overall_scores_exclude_deleted_and_avoid_full_scan(monkeypatch):
    store = _RecordingStore()
    # 3 active, 2 completed (all non-deleted) -> overall 5 total / 2 completed.
    _seed(store, 'a1', completed=False)
    _seed(store, 'a2', completed=False)
    _seed(store, 'a3', completed=False)
    _seed(store, 'c1', completed=True)
    _seed(store, 'c2', completed=True)
    # Deleted items must be excluded from both total and completed.
    _seed(store, 'd1', completed=True, deleted=True)
    _seed(store, 'd2', completed=False, deleted=True)
    install_fake_db_client(monkeypatch, store=store)

    scores = action_items_db.get_scores(_UID, date='2026-01-15')

    assert scores['overall']['total_tasks'] == 5
    assert scores['overall']['completed_tasks'] == 2
    assert scores['overall']['score'] == 40.0

    # The overall bucket must not issue an unbounded, unfiltered collection scan (the old behavior).
    unfiltered = [c for c, f in store.query_calls if c == _PATH and not f]
    assert not unfiltered, f'overall scores must not materialize the whole collection: {store.query_calls}'
