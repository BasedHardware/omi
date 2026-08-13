"""get_pending_verification_uid must not 500 on a malformed pending_verifications record.

It read datetime.fromisoformat(data['created_at']) directly, so a record missing created_at (KeyError) or
storing it as a non-string (TypeError) crashed POST /v1/phone/numbers/verify/check with a 500. It now
treats a malformed record as expired. database/phone_calls.py has a heavy import graph, so we import it
under a stub finder and patch the Firestore client.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = ('database._client', 'database.redis_db', 'database.helpers', 'utils', 'firebase_admin', 'google', 'sentry_sdk')


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
    import database.phone_calls as phone_db
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


def _doc(data):
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = data
    return doc


def _db_returning(doc):
    fake = MagicMock()
    fake.collection.return_value.document.return_value.get.return_value = doc
    return fake


def test_missing_created_at_returns_none_not_500():
    with patch.object(phone_db, 'db', _db_returning(_doc({'uid': 'u1'}))):  # no created_at
        result = phone_db.get_pending_verification_uid('+15551234567')
    assert result is None


def test_non_string_created_at_returns_none_not_500():
    with patch.object(phone_db, 'db', _db_returning(_doc({'created_at': 12345, 'uid': 'u1'}))):
        result = phone_db.get_pending_verification_uid('+15551234567')
    assert result is None


def test_valid_recent_created_at_returns_uid():
    now_iso = datetime.now(timezone.utc).isoformat()
    with patch.object(phone_db, 'db', _db_returning(_doc({'created_at': now_iso, 'uid': 'u1'}))):
        result = phone_db.get_pending_verification_uid('+15551234567')
    assert result == 'u1'


def test_naive_recent_created_at_returns_uid_not_500():
    # A parseable but timezone-naive recent created_at must not crash the aware-minus-naive subtraction.
    naive_recent = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with patch.object(phone_db, 'db', _db_returning(_doc({'created_at': naive_recent, 'uid': 'u1'}))):
        result = phone_db.get_pending_verification_uid('+15551234567')
    assert result == 'u1'


def test_naive_old_created_at_treated_expired_not_500():
    naive_old = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=365)).isoformat()
    with patch.object(phone_db, 'db', _db_returning(_doc({'created_at': naive_old, 'uid': 'u1'}))):
        result = phone_db.get_pending_verification_uid('+15551234567')
    assert result is None
