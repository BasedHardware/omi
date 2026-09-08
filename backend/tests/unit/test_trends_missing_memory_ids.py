"""Regression tests for database.trends.get_trends_data.

save_trends writes each topic in two Firestore calls (set, then update with
ArrayUnion for memory_ids), so a topic doc can exist without a memory_ids field
if the second write is interrupted or fails. get_trends_data must not raise
KeyError on such a doc, because the per-category try/except would otherwise drop
the entire category from the public /v1/trends response.
"""

import sys
from unittest.mock import MagicMock


def _install_stubs(mock_db):
    saved = {
        'database._client': sys.modules.get('database._client'),
        'firebase_admin': sys.modules.get('firebase_admin'),
        'firebase_admin.firestore': sys.modules.get('firebase_admin.firestore'),
    }
    sys.modules['database._client'] = MagicMock(db=mock_db, document_id_from_seed=lambda s: f'id-{s}')
    firebase_admin_stub = MagicMock()
    firebase_firestore_stub = MagicMock()
    firebase_firestore_stub.ArrayUnion = lambda values: values
    firebase_admin_stub.firestore = firebase_firestore_stub
    sys.modules['firebase_admin'] = firebase_admin_stub
    sys.modules['firebase_admin.firestore'] = firebase_firestore_stub
    return saved


def _restore_stubs(saved):
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod
    sys.modules.pop('database.trends', None)


def _snap(data):
    snapshot = MagicMock()
    snapshot.to_dict.return_value = data
    return snapshot


def _build_db(category, topic_docs):
    """Mock Firestore so the trends collection yields one category and its topics."""
    mock_db = MagicMock()
    trends_ref = MagicMock()
    mock_db.collection.return_value = trends_ref
    trends_ref.stream.return_value = [_snap(category)]
    category_ref = MagicMock()
    trends_ref.document.return_value = category_ref
    topics_ref = MagicMock()
    category_ref.collection.return_value = topics_ref
    topics_ref.stream.return_value = [_snap(topic) for topic in topic_docs]
    return mock_db


def test_topic_missing_memory_ids_does_not_drop_category():
    from models.trend import valid_items

    names = sorted(valid_items)
    good_topic, missing_topic = names[0], names[1]

    category = {'id': 'cat1', 'category': 'company'}
    topic_docs = [
        {'id': 't1', 'topic': good_topic, 'memory_ids': ['m1', 'm2']},
        {'id': 't2', 'topic': missing_topic},  # partial write: no memory_ids field
    ]
    saved = _install_stubs(_build_db(category, topic_docs))
    try:
        sys.modules.pop('database.trends', None)
        import database.trends as trends_db

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
    finally:
        _restore_stubs(saved)


def test_empty_memory_ids_list_counts_zero():
    from models.trend import valid_items

    topic_name = sorted(valid_items)[0]
    category = {'id': 'cat1', 'category': 'ceo'}
    topic_docs = [{'id': 't1', 'topic': topic_name, 'memory_ids': []}]
    saved = _install_stubs(_build_db(category, topic_docs))
    try:
        sys.modules.pop('database.trends', None)
        import database.trends as trends_db

        result = trends_db.get_trends_data()

        assert len(result) == 1
        assert result[0]['topics'][0]['memories_count'] == 0
        assert 'memory_ids' not in result[0]['topics'][0]
    finally:
        _restore_stubs(saved)
