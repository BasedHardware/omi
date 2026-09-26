"""Regression tests for database.trends category ID fallback, safe sequence counting, and atomic save."""

from unittest.mock import MagicMock

import database.trends as trends
from models.trend import Trend, TrendEnum, TrendType, valid_items


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
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


def test_category_missing_id_field_uses_document_snapshot_id(monkeypatch):
    good_topic = next(iter(valid_items))
    # Category document snapshot has doc.id = 'cat-fallback', but data dict lacks 'id'
    category = _Doc('cat-fallback', {'category': 'company'})
    topic_doc = _Doc('top1', {'topic': good_topic, 'memory_ids': ['m1']})

    coll = _TrendsCollection([category], {'cat-fallback': [topic_doc]})
    monkeypatch.setattr(trends, 'db', _FakeDb(coll))

    result = trends.get_trends_data()

    assert len(result) == 1
    assert result[0]['id'] == 'cat-fallback'
    assert len(result[0]['topics']) == 1
    assert result[0]['topics'][0]['topic'] == good_topic


def test_category_with_none_id_falls_back_to_snapshot_id(monkeypatch):
    good_topic = next(iter(valid_items))
    # Category document data has 'id': None
    category = _Doc('cat-snapshot-id', {'id': None, 'category': 'ceo'})
    topic_doc = _Doc('top2', {'topic': good_topic, 'memory_ids': ['m1', 'm2']})

    coll = _TrendsCollection([category], {'cat-snapshot-id': [topic_doc]})
    monkeypatch.setattr(trends, 'db', _FakeDb(coll))

    result = trends.get_trends_data()

    assert len(result) == 1
    assert result[0]['id'] == 'cat-snapshot-id'
    assert len(result[0]['topics']) == 1
    assert result[0]['topics'][0]['memories_count'] == 2


def test_topic_with_non_list_memory_ids_handles_safely(monkeypatch):
    good_topic = next(iter(valid_items))
    category = _Doc('cat1', {'id': 'cat1', 'category': 'hardware_product'})
    # Topic has integer or invalid non-list memory_ids
    topic_int = _Doc('top_int', {'topic': good_topic, 'memory_ids': 5})

    coll = _TrendsCollection([category], {'cat1': [topic_int]})
    monkeypatch.setattr(trends, 'db', _FakeDb(coll))

    result = trends.get_trends_data()

    assert len(result) == 1
    assert result[0]['topics'][0]['memories_count'] == 0


def test_save_trends_writes_topic_atomically(monkeypatch):
    fake_db = MagicMock()
    fake_trends_coll = MagicMock()
    fake_db.collection.return_value = fake_trends_coll

    fake_cat_doc = MagicMock()
    fake_trends_coll.document.return_value = fake_cat_doc

    fake_topics_coll = MagicMock()
    fake_cat_doc.collection.return_value = fake_topics_coll

    fake_topic_doc = MagicMock()
    fake_topics_coll.document.return_value = fake_topic_doc

    monkeypatch.setattr(trends, 'db', fake_db)
    monkeypatch.setattr(trends, 'document_id_from_seed', lambda s: f'seed-{s}')

    sample_trend = Trend(
        category=TrendEnum.ceo,
        type=TrendType.best,
        topics=['Elon Musk'],
    )

    trends.save_trends('mem-123', [sample_trend])

    # Category document was set with merge=True
    assert fake_cat_doc.set.called

    # Topic document was set with topic, id, AND memory_ids in single call with merge=True
    assert fake_topic_doc.set.called
    set_call_args = fake_topic_doc.set.call_args
    topic_payload = set_call_args[0][0]
    assert topic_payload['topic'] == 'Elon Musk'
    assert 'memory_ids' in topic_payload
    assert set_call_args[1].get('merge') is True

    # topic_doc.update should NOT be called (no secondary update round-trip)
    assert not fake_topic_doc.update.called
