"""Regression: a topic doc missing its 'topic' field must not drop the whole trends category.

database.trends.get_trends_data guards a missing 'memory_ids' on a topic (two-phase save can leave it
absent), but still did a required-key lookup topic['topic']. A topic missing 'topic' raised KeyError,
caught by the per-category try/except, which dropped the entire category from the public /v1/trends
response. The lookup now uses .get so only the malformed topic is skipped.
"""

import database.trends as trends
from models.trend import valid_items
from tests.store_fakes import FakeDocumentStore


def test_topic_missing_topic_key_does_not_drop_the_category(monkeypatch):
    good = next(iter(valid_items))
    store = FakeDocumentStore()
    store.set('trends/cat1', {'category': 'ceo', 'id': 'cat1'})
    store.set('trends/cat1/topics/t-missing', {'memory_ids': ['m1']})  # no 'topic' key
    store.set('trends/cat1/topics/t-good', {'topic': good, 'memory_ids': ['m2', 'm3']})
    monkeypatch.setattr(trends, '_store', lambda: store)

    result = trends.get_trends_data()

    # The category survives (before the fix the missing-topic KeyError dropped the whole category).
    assert len(result) == 1
    topics = result[0]['topics']
    assert [t['topic'] for t in topics] == [good]  # malformed topic skipped, valid one kept
    assert topics[0]['memories_count'] == 2
