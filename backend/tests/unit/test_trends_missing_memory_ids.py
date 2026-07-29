"""Regression tests for database.trends.get_trends_data.

save_trends writes each topic in two calls (set, then update with ArrayUnion for
memory_ids), so a topic doc can exist without a memory_ids field if the second
write is interrupted or fails. get_trends_data must not raise KeyError on such a
doc, because the per-category try/except would otherwise drop the entire category
from the public /v1/trends response.
"""

import database.trends as trends_db
from models.trend import valid_items
from tests.store_fakes import FakeDocumentStore


def _seed(store, category, topic_docs):
    """Seed the store so the trends collection yields one category and its topics."""
    cat_id = category['id']
    store.set(f'trends/{cat_id}', category)
    for topic in topic_docs:
        store.set(f'trends/{cat_id}/topics/{topic["id"]}', topic)


def test_topic_missing_memory_ids_does_not_drop_category(monkeypatch):
    names = sorted(valid_items)
    good_topic, missing_topic = names[0], names[1]

    category = {'id': 'cat1', 'category': 'company'}
    topic_docs = [
        {'id': 't1', 'topic': good_topic, 'memory_ids': ['m1', 'm2']},
        {'id': 't2', 'topic': missing_topic},  # partial write: no memory_ids field
    ]
    store = FakeDocumentStore()
    _seed(store, category, topic_docs)
    monkeypatch.setattr(trends_db, '_store', lambda: store)

    result = trends_db.get_trends_data()

    # The category must survive; before the fix the missing key raised
    # KeyError and the except-continue dropped the whole category.
    assert len(result) == 1
    topics = {t['topic']: t for t in result[0]['topics']}
    assert topics[good_topic]['memories_count'] == 2
    assert topics[missing_topic]['memories_count'] == 0
    # memory_ids is stripped from the response payload in both cases.
    assert 'memory_ids' not in topics[good_topic]
    assert 'memory_ids' not in topics[missing_topic]


def test_empty_memory_ids_list_counts_zero(monkeypatch):
    topic_name = sorted(valid_items)[0]
    category = {'id': 'cat1', 'category': 'ceo'}
    topic_docs = [{'id': 't1', 'topic': topic_name, 'memory_ids': []}]
    store = FakeDocumentStore()
    _seed(store, category, topic_docs)
    monkeypatch.setattr(trends_db, '_store', lambda: store)

    result = trends_db.get_trends_data()

    assert len(result) == 1
    assert result[0]['topics'][0]['memories_count'] == 0
    assert 'memory_ids' not in result[0]['topics'][0]
