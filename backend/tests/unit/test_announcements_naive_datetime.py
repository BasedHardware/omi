"""get_general_announcements must not 500 on a tz-naive last_checked_at.

GET /v1/announcements/general parses last_checked_at via
datetime.fromisoformat(last_checked_at.replace("Z", "+00:00")). When the client
sends an ISO string with no offset (e.g. "2026-01-01T00:00:00"), fromisoformat
returns a tz-NAIVE datetime. database.announcements.get_general_announcements
then compares it against the tz-AWARE Firestore created_at
(`announcement.created_at <= last_checked_at`), raising
"TypeError: can't compare offset-naive and offset-aware datetimes" -> 500.

The fix normalizes a naive last_checked_at to UTC before the comparison.

Red (without the fix): TypeError. Green (with the fix): the older announcement
is filtered out, the newer one is returned, no exception.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Stub only the heavy externals. Keep `database`, `models`, `pydantic` REAL so we
# exercise the real get_general_announcements and build a real Announcement.
_STUB = ('google', 'firebase_admin', 'redis')


def _is(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for n in list(sys.modules):
    if _is(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from database import announcements as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


class _Doc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


def _wire_docs(docs):
    """Make mod.db.collection(...).where(...).where(...).stream() return docs."""
    stream_obj = MagicMock()
    stream_obj.stream.return_value = list(docs)
    # query chain: collection().where().where() -> stream_obj
    chain = MagicMock()
    chain.where.return_value = stream_obj
    collection = MagicMock()
    collection.where.return_value = chain
    mod.db.collection.return_value = collection


def test_naive_last_checked_at_does_not_raise():
    # Firestore created_at is tz-AWARE.
    newer = _Doc(
        {
            'id': 'new',
            'type': 'announcement',
            'created_at': datetime(2026, 6, 1, tzinfo=timezone.utc),
            'active': True,
        }
    )
    older = _Doc(
        {
            'id': 'old',
            'type': 'announcement',
            'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
            'active': True,
        }
    )
    _wire_docs([newer, older])

    # Client-supplied last_checked_at with NO offset -> tz-NAIVE (this is what
    # datetime.fromisoformat("2026-03-01T00:00:00") returns in the router).
    naive_last_checked = datetime(2026, 3, 1)
    assert naive_last_checked.tzinfo is None

    # Without the fix this raises TypeError (naive vs aware comparison).
    result = mod.get_general_announcements(naive_last_checked)

    # With the fix: only the announcement created AFTER last_checked_at is returned.
    ids = [a.id for a in result]
    assert ids == ['new']


def test_naive_returns_all_when_before_everything():
    older = _Doc(
        {
            'id': 'a',
            'type': 'announcement',
            'created_at': datetime(2026, 6, 1, tzinfo=timezone.utc),
            'active': True,
        }
    )
    _wire_docs([older])

    naive_last_checked = datetime(2025, 1, 1)  # naive, before everything
    assert naive_last_checked.tzinfo is None

    result = mod.get_general_announcements(naive_last_checked)
    assert [a.id for a in result] == ['a']
