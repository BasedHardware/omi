"""Regression: a topic doc missing its 'topic' field must not drop the whole trends category.

database.trends.get_trends_data guards a missing 'memory_ids' on a topic (two-phase save can leave it
absent), but still did a required-key lookup topic['topic']. A topic missing 'topic' raised KeyError,
caught by the per-category try/except, which dropped the entire category from the public /v1/trends
response. The lookup now uses .get so only the malformed topic is skipped.
"""

import database.trends as trends
from models.trend import valid_items


class _Doc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _DocRef:
    def __init__(self, topics):
        self._topics = topics

    def collection(self, _name):
        return _TopicsCollection(self._topics)


class _TopicsCollection:
    def __init__(self, topics):
        self._topics = topics

    def stream(self, retry=None):
        return iter(self._topics)


class _TrendsCollection:
    def __init__(self, categories, topics_by_cat):
        self._categories = categories
        self._topics_by_cat = topics_by_cat

    def stream(self, retry=None):
        return iter(self._categories)

    def document(self, cat_id):
        return _DocRef(self._topics_by_cat.get(cat_id, []))


class _FakeDb:
    def __init__(self, collection):
        self._collection = collection

    def collection(self, _name):
        return self._collection


def test_topic_missing_topic_key_does_not_drop_the_category(monkeypatch):
    good = next(iter(valid_items))
    category = _Doc({'category': 'ceo', 'id': 'cat1'})
    topic_missing = _Doc({'memory_ids': ['m1']})  # no 'topic' key -> KeyError before the fix
    topic_good = _Doc({'topic': good, 'memory_ids': ['m2', 'm3']})
    coll = _TrendsCollection([category], {'cat1': [topic_missing, topic_good]})
    monkeypatch.setattr(trends, 'db', _FakeDb(coll))

    result = trends.get_trends_data()

    # The category survives (before the fix the missing-topic KeyError dropped the whole category).
    assert len(result) == 1
    topics = result[0]['topics']
    assert [t['topic'] for t in topics] == [good]  # malformed topic skipped, valid one kept
    assert topics[0]['memories_count'] == 2
