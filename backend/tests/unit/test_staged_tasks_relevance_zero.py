"""Regression test: migrate_ai_tasks must keep the best (relevance_score == 0) AI task.

database.staged_tasks.migrate_ai_tasks keeps the top 3 AI action items by relevance_score
ascending (best first) and moves the rest to staged_tasks. The sort key used
`x.get('relevance_score') or 999`, which coerces a valid best score of 0 (relevance_score is
an int in 0-1000 where 0 is most relevant) to 999, sorting the single most relevant task last
so it gets moved out of action_items instead of kept. The key now maps only a genuinely missing
(None) score to 999.

Seam: database.staged_tasks reads/writes exclusively through the ``_store()`` port seam, so an
in-memory FakeDocumentStore seeded with action-item docs exercises the real migration path and a
"move out of action_items" is observable as the doc landing in the staged_tasks collection.
"""

import database.staged_tasks as staged_tasks
from tests.store_fakes import FakeDocumentStore


def _seed(monkeypatch, action_docs):
    store = FakeDocumentStore()
    for doc_id, data in action_docs:
        store.set(f'users/u1/action_items/{doc_id}', {'completed': False, **data})
    monkeypatch.setattr(staged_tasks, '_store', lambda: store)
    return store


def test_migrate_keeps_relevance_zero_task(monkeypatch):
    # Five AI tasks; ascending best-first means score 0 is the single best and must be kept.
    store = _seed(
        monkeypatch,
        [
            ('t0', {'source': 'screenshot', 'relevance_score': 0}),  # best (0)
            ('t1', {'source': 'screenshot', 'relevance_score': 1}),
            ('t2', {'source': 'screenshot', 'relevance_score': 2}),
            ('t3', {'source': 'screenshot', 'relevance_score': 3}),
            ('t4', {'source': 'screenshot', 'relevance_score': 4}),
        ],
    )

    staged_tasks.migrate_ai_tasks('u1')

    moved_ids = set(store.list_ids('users/u1/staged_tasks'))
    # Keep the three lowest scores (t0, t1, t2); move the rest. The best (t0, score 0)
    # must NOT be moved out. With the old `or 999` key it sorted last and was moved.
    assert 't0' not in moved_ids
    assert moved_ids == {'t3', 't4'}


def test_migrate_still_sorts_missing_score_last(monkeypatch):
    # A genuinely missing score must still sort last (moved), distinct from a 0.
    store = _seed(
        monkeypatch,
        [
            ('z', {'source': 'screenshot', 'relevance_score': 0}),
            ('a', {'source': 'screenshot', 'relevance_score': 5}),
            ('b', {'source': 'screenshot', 'relevance_score': 7}),
            ('none', {'source': 'screenshot'}),  # missing relevance_score
        ],
    )

    staged_tasks.migrate_ai_tasks('u1')

    # Keep z(0), a(5), b(7); the missing-score task sorts last and is moved.
    assert store.list_ids('users/u1/staged_tasks') == ['none']
