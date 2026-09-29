import os
import sys
import types
from pathlib import Path
import unittest
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _setup_preflight_stubs():
    if "pydantic" not in sys.modules:
        try:
            import pydantic
        except ModuleNotFoundError:
            pyd_mod = _mod("pydantic")

            class _BaseModel:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items():
                        setattr(self, k, v)

                @classmethod
                def model_construct(cls, **kwargs):
                    inst = cls.__new__(cls)
                    for k, v in kwargs.items():
                        setattr(inst, k, v)
                    return inst

            pyd_mod.BaseModel = _BaseModel
            pyd_mod.Field = lambda *args, **kwargs: kwargs.get("default", None)
            sys.modules["pydantic"] = pyd_mod

    if "google.api_core.retry" not in sys.modules:
        try:
            import google.api_core.retry
        except ModuleNotFoundError:
            _pkg("google")
            _pkg("google.api_core")
            retry_mod = _mod("google.api_core.retry")
            if not hasattr(retry_mod, "Retry"):
                retry_mod.Retry = MagicMock()


_setup_preflight_stubs()

from models.trend import Trend, TrendEnum, TrendType, valid_items


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


class TestTrendsAtomicResilience(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.saved_stubs = _install_stubs(self.mock_db)
        sys.modules.pop('database.trends', None)
        import database.trends as trends_mod

        self.trends_mod = trends_mod

    def tearDown(self):
        _restore_stubs(self.saved_stubs)

    def test_save_trends_atomic_set_with_array_union(self):
        """save_trends writes topic doc with ArrayUnion in a single atomic set(merge=True) call and does not call update."""
        mock_trends_coll = MagicMock()
        self.mock_db.collection.return_value = mock_trends_coll
        category_doc = MagicMock()
        topic_doc = MagicMock()
        topics_coll = MagicMock()

        mock_trends_coll.document.return_value = category_doc
        category_doc.collection.return_value = topics_coll
        topics_coll.document.return_value = topic_doc

        trend = Trend(category=TrendEnum.company, topics=['Tesla'], type=TrendType.best)
        self.trends_mod.save_trends('mem-123', [trend])

        # Category doc set
        category_doc.set.assert_called_once()
        cat_payload = category_doc.set.call_args[0][0]
        self.assertEqual(cat_payload['category'], 'company')
        self.assertEqual(cat_payload['type'], 'best')

        # Topic doc set must be called with merge=True containing id, topic, and memory_ids
        topic_doc.set.assert_called_once()
        topic_payload = topic_doc.set.call_args[0][0]
        topic_kwargs = topic_doc.set.call_args[1]
        self.assertTrue(topic_kwargs.get('merge'))
        self.assertEqual(topic_payload['id'], 'id-Tesla')
        self.assertEqual(topic_payload['topic'], 'Tesla')
        mem_ids = topic_payload['memory_ids']
        self.assertEqual(list(getattr(mem_ids, 'values', mem_ids)), ['mem-123'])

        # update() must NOT be called on topic doc (eliminating the two-phase write)
        topic_doc.update.assert_not_called()

    def test_save_trends_empty_or_whitespace_memory_id(self):
        """save_trends aborts cleanly if memory_id is empty or whitespace."""
        mock_trends_coll = MagicMock()
        self.mock_db.collection.return_value = mock_trends_coll

        trend = Trend(category=TrendEnum.company, topics=['Tesla'], type=TrendType.best)
        self.trends_mod.save_trends('', [trend])
        self.trends_mod.save_trends('   ', [trend])
        self.trends_mod.save_trends(None, [trend])  # type: ignore

        mock_trends_coll.document.assert_not_called()

    def test_save_trends_empty_trends_list(self):
        """save_trends aborts cleanly if trends list is empty or None."""
        mock_trends_coll = MagicMock()
        self.mock_db.collection.return_value = mock_trends_coll

        self.trends_mod.save_trends('mem-123', [])
        self.trends_mod.save_trends('mem-123', None)  # type: ignore

        mock_trends_coll.document.assert_not_called()

    def test_save_trends_skips_invalid_topics(self):
        """save_trends skips empty, non-string, or whitespace-only topics."""
        mock_trends_coll = MagicMock()
        self.mock_db.collection.return_value = mock_trends_coll
        category_doc = MagicMock()
        topic_doc = MagicMock()
        topics_coll = MagicMock()

        mock_trends_coll.document.return_value = category_doc
        category_doc.collection.return_value = topics_coll
        topics_coll.document.return_value = topic_doc

        trend = Trend.model_construct(
            category=TrendEnum.company,
            topics=['', '   ', None, 'Tesla', 123],
            type=TrendType.best,
        )
        self.trends_mod.save_trends('mem-123', [trend])

        # Only 'Tesla' should be saved
        self.assertEqual(topics_coll.document.call_count, 1)
        self.assertEqual(topics_coll.document.call_args[0][0], 'id-Tesla')
        self.assertEqual(topic_doc.set.call_count, 1)

    def test_save_trends_trims_whitespace(self):
        """save_trends strips leading and trailing whitespace from memory_id and topic."""
        mock_trends_coll = MagicMock()
        self.mock_db.collection.return_value = mock_trends_coll
        category_doc = MagicMock()
        topic_doc = MagicMock()
        topics_coll = MagicMock()

        mock_trends_coll.document.return_value = category_doc
        category_doc.collection.return_value = topics_coll
        topics_coll.document.return_value = topic_doc

        trend = Trend(category=TrendEnum.company, topics=['  Tesla  '], type=TrendType.best)
        self.trends_mod.save_trends('  mem-456  ', [trend])

        topic_payload = topic_doc.set.call_args[0][0]
        self.assertEqual(topic_payload['topic'], 'Tesla')
        mem_ids = topic_payload['memory_ids']
        self.assertEqual(list(getattr(mem_ids, 'values', mem_ids)), ['mem-456'])

    def test_get_trends_data_guards_missing_category_id(self):
        """get_trends_data handles category doc without 'id' gracefully without raising KeyError."""
        cat_snap = MagicMock()
        cat_snap.to_dict.return_value = {'category': 'company'}  # missing 'id'
        cat_snap.id = 'cat-fallback-id'

        trends_ref = MagicMock()
        self.mock_db.collection.return_value = trends_ref
        trends_ref.stream.return_value = [cat_snap]

        category_doc_ref = MagicMock()
        trends_ref.document.return_value = category_doc_ref
        topics_ref = MagicMock()
        category_doc_ref.collection.return_value = topics_ref
        topics_ref.stream.return_value = []

        result = self.trends_mod.get_trends_data()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['category'], 'company')

    def test_get_trends_data_guards_non_list_memory_ids(self):
        """get_trends_data handles topic doc where memory_ids is malformed (e.g. int/bool/str) without raising TypeError."""
        good_topic = sorted(valid_items)[0]
        cat_snap = MagicMock()
        cat_snap.to_dict.return_value = {'id': 'cat1', 'category': 'ceo'}

        topic1_snap = MagicMock()
        topic1_snap.to_dict.return_value = {'id': 't1', 'topic': good_topic, 'memory_ids': 42}  # invalid int type

        trends_ref = MagicMock()
        self.mock_db.collection.return_value = trends_ref
        trends_ref.stream.return_value = [cat_snap]

        category_doc_ref = MagicMock()
        trends_ref.document.return_value = category_doc_ref
        topics_ref = MagicMock()
        category_doc_ref.collection.return_value = topics_ref
        topics_ref.stream.return_value = [topic1_snap]

        result = self.trends_mod.get_trends_data()
        self.assertEqual(len(result), 1)
        topics = result[0]['topics']
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]['memories_count'], 0)

    def test_get_trends_data_sorts_descending_by_memories_count(self):
        """get_trends_data sorts topics descending by memories count."""
        topics_list = sorted(valid_items)[:3]
        cat_snap = MagicMock()
        cat_snap.to_dict.return_value = {'id': 'cat1', 'category': 'company'}

        t1_snap = MagicMock()
        t1_snap.to_dict.return_value = {'id': 't1', 'topic': topics_list[0], 'memory_ids': ['m1']}
        t2_snap = MagicMock()
        t2_snap.to_dict.return_value = {'id': 't2', 'topic': topics_list[1], 'memory_ids': ['m1', 'm2', 'm3']}
        t3_snap = MagicMock()
        t3_snap.to_dict.return_value = {'id': 't3', 'topic': topics_list[2], 'memory_ids': ['m1', 'm2']}

        trends_ref = MagicMock()
        self.mock_db.collection.return_value = trends_ref
        trends_ref.stream.return_value = [cat_snap]

        category_doc_ref = MagicMock()
        trends_ref.document.return_value = category_doc_ref
        topics_ref = MagicMock()
        category_doc_ref.collection.return_value = topics_ref
        topics_ref.stream.return_value = [t1_snap, t2_snap, t3_snap]

        result = self.trends_mod.get_trends_data()
        self.assertEqual(len(result), 1)
        topics = result[0]['topics']
        self.assertEqual([t['topic'] for t in topics], [topics_list[1], topics_list[2], topics_list[0]])
        self.assertEqual([t['memories_count'] for t in topics], [3, 2, 1])

    def test_get_trends_data_filters_invalid_topics(self):
        """get_trends_data filters out topics that are not in valid_items."""
        good_topic = sorted(valid_items)[0]
        cat_snap = MagicMock()
        cat_snap.to_dict.return_value = {'id': 'cat1', 'category': 'company'}

        good_snap = MagicMock()
        good_snap.to_dict.return_value = {'id': 't1', 'topic': good_topic, 'memory_ids': ['m1']}
        invalid_snap = MagicMock()
        invalid_snap.to_dict.return_value = {
            'id': 't2',
            'topic': 'TotallyNonExistentRandomTopic12345',
            'memory_ids': ['m2'],
        }

        trends_ref = MagicMock()
        self.mock_db.collection.return_value = trends_ref
        trends_ref.stream.return_value = [cat_snap]

        category_doc_ref = MagicMock()
        trends_ref.document.return_value = category_doc_ref
        topics_ref = MagicMock()
        category_doc_ref.collection.return_value = topics_ref
        topics_ref.stream.return_value = [good_snap, invalid_snap]

        result = self.trends_mod.get_trends_data()
        self.assertEqual(len(result), 1)
        topics = result[0]['topics']
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]['topic'], good_topic)


if __name__ == '__main__':
    unittest.main()
