"""GET /v1/trends (database.trends.get_trends_data) must not drop an entire category
when a single sibling topic doc is malformed.

On main the topic sort key is ``len(e['memory_ids'])`` and the loop reads ``topic['topic']`` /
``topic['memory_ids']`` directly. One topic doc missing ``memory_ids`` raises KeyError inside the
sort, which is swallowed by the outer ``except Exception`` so the WHOLE category (including every
valid topic) is discarded from the response. The fix sorts/parses per-topic with ``.get(...)`` and a
per-topic try/except so a malformed sibling is skipped while the valid topics survive.

database/trends.py has a heavy import graph (firebase_admin, google), so we import it under a stub finder.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Stub only database/trends.py's heavy dependencies, NOT the whole 'database' package,
# so database.trends itself loads for real. It imports database._client (db,
# document_id_from_seed), firebase_admin, and google.api_core.retry. models.trend is pure
# pydantic, so we leave it real (we rely on its real valid_items set).
_STUB = (
    'database._client',
    'firebase_admin',
    'google',
    'sentry_sdk',
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from database import trends as trends_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


class _Doc:
    """Stand-in for a Firestore document snapshot whose .to_dict() returns a fixed dict."""

    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _TopicsCollection:
    def __init__(self, topic_docs):
        self._topic_docs = topic_docs

    def stream(self, *args, **kwargs):
        return iter(self._topic_docs)


class _CategoryRef:
    """Returned by trends_ref.document(category_id); .collection('topics') yields the topics."""

    def __init__(self, topic_docs):
        self._topics = _TopicsCollection(topic_docs)

    def collection(self, name):
        assert name == 'topics'
        return self._topics


class _TrendsRef:
    def __init__(self, category_docs, topic_docs_by_category_id):
        self._category_docs = category_docs
        self._topic_docs_by_category_id = topic_docs_by_category_id

    def stream(self, *args, **kwargs):
        return iter(self._category_docs)

    def document(self, category_id):
        return _CategoryRef(self._topic_docs_by_category_id[category_id])


class _FakeDB:
    def __init__(self, category_docs, topic_docs_by_category_id):
        self._ref = _TrendsRef(category_docs, topic_docs_by_category_id)

    def collection(self, name):
        assert name == 'trends'
        return self._ref


def test_malformed_topic_does_not_drop_whole_category():
    # 'OpenAI' is in valid_items (company_options); use it as the good topic.
    good_topic = {'id': 't_good', 'topic': 'OpenAI', 'memory_ids': ['m1', 'm2']}
    # Malformed sibling: missing 'memory_ids' entirely -> on main the sort key len(e['memory_ids'])
    # raises KeyError, which the outer except swallows, dropping the whole category.
    bad_topic = {'id': 't_bad', 'topic': 'OpenAI'}

    category = {'id': 'cat1', 'category': 'company'}
    fake_db = _FakeDB(
        category_docs=[_Doc(category)],
        topic_docs_by_category_id={'cat1': [_Doc(good_topic), _Doc(bad_topic)]},
    )

    with patch.object(trends_mod, 'db', fake_db):
        result = trends_mod.get_trends_data()

    # The category must survive (not be dropped wholesale).
    assert len(result) == 1, "the category was dropped entirely because of one malformed topic"
    cat = result[0]
    assert cat['category'] == 'company'

    topics = cat['topics']
    returned_topic_ids = [t['id'] for t in topics]
    # The good topic must still be present.
    assert 't_good' in returned_topic_ids, "the valid topic was lost when a sibling was malformed"

    good = next(t for t in topics if t['id'] == 't_good')
    assert good['memories_count'] == 2
    assert 'memory_ids' not in good
