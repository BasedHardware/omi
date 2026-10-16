"""Issue #21708 — hidden rows inside a raw index window must not shrink
the visible page.

list_memory_updated_or_created_index used to stream `limit + offset`
RAW rows, drop rejected/invalidated rows, and return whatever survived —
a hidden row cost the page a visible slot and callers read the short
page as end-of-data (m4/m5/m6 unreachable in the repro below). The
window now grows until the page is full or both ordered streams are
exhausted. Same class as #12714 (scoring_desc), now fixed for the
updated/created index.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

_STUB = (
    'firebase_admin',
    'google',
    'pusher',
    'modal',
    'ulid',
    'redis',
    'prometheus_client',
    'cachetools',
    'sentry_sdk',
    'pydub',
    'opuslib',
    'pinecone',
    'typesense',
)


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
        if any(name == p or name.startswith(p + '.') for p in _STUB):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
_f = _Finder()
sys.meta_path.insert(0, _f)
try:
    import database.memories as mem_db
finally:
    if _f in sys.meta_path:
        sys.meta_path.remove(_f)


class _Doc:
    def __init__(self, payload):
        self.id = payload['id']
        self._p = payload

    def to_dict(self):
        return dict(self._p)


def _mem(mid, *, hidden=None, has_updated=True, order=0):
    d = {'id': mid, 'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc) - timedelta(days=order)}
    if has_updated:
        d['updated_at'] = d['created_at'] + timedelta(hours=1)
    if hidden == 'rejected':
        d['user_review'] = False
    elif hidden == 'invalid':
        d['invalid_at'] = datetime(2026, 2, 1, tzinfo=timezone.utc)
    return d


def _install_streams(monkeypatch, updated_docs, created_docs):
    """Ordered fake windows: each stream returns its first `candidate_limit` rows."""

    def fake_stream(ref, order_field, candidate_limit, *, budget=None):
        src = updated_docs if order_field == 'updated_at' else created_docs
        return [_Doc(d) for d in src[:candidate_limit]]

    monkeypatch.setattr(mem_db, '_stream_memory_list_index_window', fake_stream)
    monkeypatch.setattr(mem_db, '_get_db', lambda client=None: MagicMock())


class TestHiddenRowsDontShrinkPages:
    def test_rejected_and_invalid_rows_dont_cost_visible_slots(self, monkeypatch):
        # The issue's repro: m1..m6 newest-first; m2 rejected, m3 invalid,
        # m5 has no updated_at. Expected visible order: m1, m4, m5, m6.
        m1 = _mem('m1', order=0)
        m2 = _mem('m2', hidden='rejected', order=1)
        m3 = _mem('m3', hidden='invalid', order=2)
        m4 = _mem('m4', order=3)
        m5 = _mem('m5', has_updated=False, order=4)
        m6 = _mem('m6', order=5)
        updated = [m1, m2, m3, m4, m6]  # updated_at DESC (m5 lacks it)
        created = [m1, m2, m3, m4, m5, m6]  # created_at DESC
        _install_streams(monkeypatch, updated, created)

        page = mem_db.list_memory_updated_or_created_index('u1', limit=3, offset=0)
        assert [m['id'] for m in page] == ['m1', 'm4', 'm5']

        p2 = mem_db.list_memory_updated_or_created_index('u1', limit=2, offset=0)
        p3 = mem_db.list_memory_updated_or_created_index('u1', limit=2, offset=2)
        assert [m['id'] for m in p2] == ['m1', 'm4']
        assert [m['id'] for m in p3] == ['m5', 'm6']

    def test_clean_page_pays_one_pass(self, monkeypatch):
        """No hidden rows → the window never regrows (read cost unchanged)."""
        calls = []
        docs = [_mem(f'm{i}', order=i) for i in range(10)]

        def counting_stream(ref, order_field, candidate_limit, *, budget=None):
            calls.append((order_field, candidate_limit))
            src = docs if order_field == 'updated_at' else docs
            return [_Doc(d) for d in src[:candidate_limit]]

        monkeypatch.setattr(mem_db, '_stream_memory_list_index_window', counting_stream)
        monkeypatch.setattr(mem_db, '_get_db', lambda client=None: MagicMock())

        page = mem_db.list_memory_updated_or_created_index('u1', limit=3, offset=0)
        assert [m['id'] for m in page] == ['m0', 'm1', 'm2']
        assert calls == [
            ('updated_at', 3),
            ('created_at', 3),
        ], 'a clean page must pay exactly the needed window, no growth'
