"""Hermetic unit tests for input validation, NotFound error resilience, and merge writes in database/phone_calls.py."""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = ('database._client', 'database.redis_db', 'database.helpers', 'utils', 'firebase_admin', 'sentry_sdk')


def _is_stubbed_name(name: str) -> bool:
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

    def __getattr__(self, name: str):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        if name in ('set_data_protection_level', 'prepare_for_write', 'prepare_for_read'):

            def _pass_through_decorator(*args, **kwargs):
                return lambda func: func

            return _pass_through_decorator
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


def _make_mock_doc(exists: bool = True, data: dict | None = None, doc_id: str = "doc-1"):
    doc = MagicMock()
    doc.exists = exists
    doc.id = doc_id
    doc.to_dict.return_value = data if data is not None else {}
    return doc


# ---------------------------------------------------------------------------
# _hash_phone_number validation
# ---------------------------------------------------------------------------


def test_hash_phone_number_rejects_non_string():
    with pytest.raises(ValueError, match="phone_number must be a string"):
        phone_db._hash_phone_number(None)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="phone_number must be a string"):
        phone_db._hash_phone_number(12345)  # type: ignore[arg-type]


def test_hash_phone_number_deterministic():
    h1 = phone_db._hash_phone_number("+15551234567")
    h2 = phone_db._hash_phone_number("+15551234567")
    assert h1 == h2
    assert len(h1) == 64


def test_hash_phone_number_normalizes_whitespace():
    h1 = phone_db._hash_phone_number("+15551234567")
    h2 = phone_db._hash_phone_number("   +15551234567   ")
    assert h1 == h2


def test_prepare_phone_number_for_write_normalizes_hash_parity():
    raw_data = {"phone_number": "   +15551234567   "}
    prepared = phone_db._prepare_phone_number_for_write(raw_data, "user-1", "enhanced")
    expected_hash = phone_db._hash_phone_number("+15551234567")
    assert prepared["phone_number_hash"] == expected_hash


# ---------------------------------------------------------------------------
# upsert_phone_number validation and merge writes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_upsert_phone_number_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        phone_db.upsert_phone_number(invalid_uid, {"id": "p1", "phone_number": "+15551234567"})  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_data", [None, "not-a-dict", 123, []])
def test_upsert_phone_number_rejects_invalid_data(invalid_data):
    with pytest.raises(ValueError, match="phone_number_data must be a dictionary"):
        phone_db.upsert_phone_number("u1", invalid_data)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123])
def test_upsert_phone_number_rejects_invalid_id(invalid_id):
    with pytest.raises(ValueError, match="phone_number_data must contain a non-empty string id"):
        phone_db.upsert_phone_number("u1", {"id": invalid_id, "phone_number": "+15551234567"})


def test_upsert_phone_number_writes_with_merge_and_stripped_ids():
    fake_db = MagicMock()
    user_doc_ref = MagicMock()
    phone_doc_ref = MagicMock()
    fake_db.collection.return_value.document.return_value = user_doc_ref
    user_doc_ref.collection.return_value.document.return_value = phone_doc_ref

    with patch.object(phone_db, "db", fake_db):
        phone_db.upsert_phone_number("  user-123  ", {"id": "  phone-456  ", "phone_number": "+15551234567"})

    fake_db.collection.assert_called_with("users")
    fake_db.collection.return_value.document.assert_called_with("user-123")
    user_doc_ref.collection.assert_called_with("phone_numbers")
    user_doc_ref.collection.return_value.document.assert_called_with("phone-456")
    phone_doc_ref.set.assert_called_once()
    _, kwargs = phone_doc_ref.set.call_args
    assert kwargs.get("merge") is True


# ---------------------------------------------------------------------------
# get_phone_numbers safe defaults
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_get_phone_numbers_invalid_uid_returns_empty(invalid_uid):
    fake_db = MagicMock()
    with patch.object(phone_db, "db", fake_db):
        assert phone_db.get_phone_numbers(invalid_uid) == []  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_get_phone_numbers_skips_non_dict_snapshots():
    fake_db = MagicMock()
    snap1 = _make_mock_doc(exists=True, data={"id": "p1", "phone_number": "+111"})
    snap2 = MagicMock()
    snap2.to_dict.return_value = None  # non-dict
    fake_db.collection.return_value.document.return_value.collection.return_value.stream.return_value = [snap1, snap2]

    with patch.object(phone_db, "db", fake_db):
        res = phone_db.get_phone_numbers("u1")
    assert len(res) == 1
    assert res[0]["id"] == "p1"


# ---------------------------------------------------------------------------
# get_phone_number safe defaults
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_get_phone_number_invalid_uid_returns_none(invalid_uid):
    fake_db = MagicMock()
    with patch.object(phone_db, "db", fake_db):
        assert phone_db.get_phone_number(invalid_uid, "p1") is None  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123])
def test_get_phone_number_invalid_id_returns_none(invalid_id):
    fake_db = MagicMock()
    with patch.object(phone_db, "db", fake_db):
        assert phone_db.get_phone_number("u1", invalid_id) is None  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_get_phone_number_returns_none_when_not_exists():
    fake_db = MagicMock()
    doc = _make_mock_doc(exists=False)
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        doc
    )
    with patch.object(phone_db, "db", fake_db):
        assert phone_db.get_phone_number("u1", "p1") is None


# ---------------------------------------------------------------------------
# get_phone_number_by_number safe defaults and lookups
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_arg", [None, "", "   ", 123])
def test_get_phone_number_by_number_invalid_inputs_returns_none(invalid_arg):
    fake_db = MagicMock()
    with patch.object(phone_db, "db", fake_db):
        assert phone_db.get_phone_number_by_number(invalid_arg, "+15551234567") is None  # type: ignore[arg-type]
        assert phone_db.get_phone_number_by_number("u1", invalid_arg) is None  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_get_phone_number_by_number_handles_none_phone_without_attribute_error():
    fake_db = MagicMock()
    with patch.object(phone_db, "db", fake_db):
        # Passing None directly must not raise AttributeError in _hash_phone_number
        assert phone_db.get_phone_number_by_number("u1", None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# delete_phone_number validation and NotFound resilience
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_delete_phone_number_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        phone_db.delete_phone_number(invalid_uid, "p1")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123])
def test_delete_phone_number_rejects_invalid_id(invalid_id):
    with pytest.raises(ValueError, match="phone_number_id must be a non-empty string"):
        phone_db.delete_phone_number("u1", invalid_id)  # type: ignore[arg-type]


def test_delete_phone_number_swallows_not_found():
    fake_db = MagicMock()
    phone_doc_ref = MagicMock()
    phone_doc_ref.delete.side_effect = NotFound("Document missing")
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = phone_doc_ref

    with patch.object(phone_db, "db", fake_db):
        phone_db.delete_phone_number("u1", "p1")  # must not raise


# ---------------------------------------------------------------------------
# get_primary_phone_number safe defaults
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_get_primary_phone_number_invalid_uid_returns_none(invalid_uid):
    fake_db = MagicMock()
    with patch.object(phone_db, "db", fake_db):
        assert phone_db.get_primary_phone_number(invalid_uid) is None  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


# ---------------------------------------------------------------------------
# set_pending_verification validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_set_pending_verification_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        phone_db.set_pending_verification(invalid_uid, "+15551234567")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_phone", [None, "", "   ", 123])
def test_set_pending_verification_rejects_invalid_phone(invalid_phone):
    with pytest.raises(ValueError, match="phone_number must be a non-empty string"):
        phone_db.set_pending_verification("u1", invalid_phone)  # type: ignore[arg-type]


def test_set_pending_verification_stores_hashed_doc():
    fake_db = MagicMock()
    doc_ref = MagicMock()
    fake_db.collection.return_value.document.return_value = doc_ref

    with patch.object(phone_db, "db", fake_db):
        phone_db.set_pending_verification("  u1  ", "  +15551234567  ")

    expected_hash = phone_db._hash_phone_number("+15551234567")
    fake_db.collection.assert_called_with("pending_verifications")
    fake_db.collection.return_value.document.assert_called_with(expected_hash)
    doc_ref.set.assert_called_once()
    payload = doc_ref.set.call_args[0][0]
    assert payload["uid"] == "u1"
    assert payload["phone_number_hash"] == expected_hash


# ---------------------------------------------------------------------------
# get_pending_verification_uid safe defaults and NotFound resilience
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_phone", [None, "", "   ", 123])
def test_get_pending_verification_uid_invalid_phone_returns_none(invalid_phone):
    fake_db = MagicMock()
    with patch.object(phone_db, "db", fake_db):
        assert phone_db.get_pending_verification_uid(invalid_phone) is None  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_get_pending_verification_uid_swallows_not_found_on_expired_delete():
    fake_db = MagicMock()
    doc_ref = MagicMock()
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    doc_ref.get.return_value = _make_mock_doc(exists=True, data={"uid": "u1", "created_at": old_iso})
    doc_ref.delete.side_effect = NotFound("Already pruned")
    fake_db.collection.return_value.document.return_value = doc_ref

    with patch.object(phone_db, "db", fake_db):
        assert phone_db.get_pending_verification_uid("+15551234567") is None  # must not raise


# ---------------------------------------------------------------------------
# delete_pending_verification safe defaults and NotFound resilience
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_phone", [None, "", "   ", 123])
def test_delete_pending_verification_invalid_phone_no_op(invalid_phone):
    fake_db = MagicMock()
    with patch.object(phone_db, "db", fake_db):
        phone_db.delete_pending_verification(invalid_phone)  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_delete_pending_verification_swallows_not_found():
    fake_db = MagicMock()
    doc_ref = MagicMock()
    doc_ref.delete.side_effect = NotFound("Already pruned")
    fake_db.collection.return_value.document.return_value = doc_ref

    with patch.object(phone_db, "db", fake_db):
        phone_db.delete_pending_verification("+15551234567")  # must not raise
