"""mark_all_advice_read must page the unread set instead of materializing all of it before the
first commit (unbounded memory for a large backlog).

Each committed page flips its docs to is_read=True, leaving the is_read==False set, so re-running the
same bounded query drains the backlog a page at a time. Exercised through the ADR-0044 facade seam
(install_fake_db_client, store=): db...limit().stream() lands on store.query(), so a recording fake
counts the pages.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.advice as advice  # noqa: E402
from tests.store_fakes import FakeDocumentStore, install_fake_db_client  # noqa: E402

_UID = 'u'


class _RecordingStore(FakeDocumentStore):
    def __init__(self):
        super().__init__()
        self.query_calls = 0

    def query(self, collection, *, filters=None, **kwargs):
        self.query_calls += 1
        return super().query(collection, filters=filters, **kwargs)


def _seed_unread(store, n):
    for i in range(n):
        store._docs[f'users/{_UID}/advice/adv{i}'] = {'is_read': False, 'content': f'c{i}'}


def test_marks_all_unread_and_pages_in_bounded_chunks(monkeypatch):
    monkeypatch.setattr(advice, 'BATCH_LIMIT', 2)  # force multiple pages over 5 docs
    store = _RecordingStore()
    _seed_unread(store, 5)
    install_fake_db_client(monkeypatch, store=store)

    total = advice.mark_all_advice_read(_UID)

    assert total == 5
    assert all(d['is_read'] is True for p, d in store._docs.items() if p.startswith(f'users/{_UID}/advice/'))
    # 5 docs / page size 2 => pages of 2, 2, 1 (the last short page ends the loop): 3 queries.
    assert store.query_calls == 3, f'expected bounded paging, got {store.query_calls} queries'


def test_empty_unread_set_makes_a_single_bounded_query(monkeypatch):
    store = _RecordingStore()
    install_fake_db_client(monkeypatch, store=store)

    assert advice.mark_all_advice_read(_UID) == 0
    assert store.query_calls == 1


def test_exact_multiple_of_page_size_terminates(monkeypatch):
    monkeypatch.setattr(advice, 'BATCH_LIMIT', 2)
    store = _RecordingStore()
    _seed_unread(store, 4)  # exactly two full pages, then an empty probe
    install_fake_db_client(monkeypatch, store=store)

    assert advice.mark_all_advice_read(_UID) == 4
    # pages of 2, 2 (both full), then one empty query returns [] and stops: 3 queries.
    assert store.query_calls == 3


def test_page_cap_bounds_a_pathological_unread_flood(monkeypatch):
    # cubic PR 10887 E4: if concurrent creation keeps every page full, the self-draining loop could
    # spin forever holding the request. The page cap bounds it. Model a store whose unread set never
    # empties (full page every query, the is_read flip ignored).
    from database.store.records import StoredDocument

    monkeypatch.setattr(advice, 'BATCH_LIMIT', 2)
    monkeypatch.setattr(advice, '_MAX_MARK_READ_PAGES', 3)

    class _FloodStore(FakeDocumentStore):
        def query(self, collection, *, filters=None, **kwargs):
            limit = kwargs.get('limit') or 2
            return [StoredDocument.present(f'{collection}/a{i}', {'is_read': False}) for i in range(limit)]

        def update(self, path, data, *, if_updated_at=None):
            pass  # ignore the flip -> the unread set never drains

        def _update(self, path, data, *, if_updated_at=None, session=None):
            pass

    install_fake_db_client(monkeypatch, store=_FloodStore())
    total = advice.mark_all_advice_read(_UID)
    assert total == 3 * 2  # stopped at the 3-page cap (BATCH_LIMIT=2), did not spin
