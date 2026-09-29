"""Hermetic unit tests for live STT language profile database resilience."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import pytest

from database.live_language_profile import (
    FIELD,
    MAX_CODES,
    MAX_COUNT,
    MAX_SESSIONS,
    _append_transaction,
    _clean_counts,
    _clean_id,
    _clean_sessions,
    _resolve_client,
    append_live_language_session,
    get_live_language_sessions,
    invalidate_live_language_sessions_cache,
)


def test_clean_id_validation():
    assert _clean_id(None) is None
    assert _clean_id(123) is None
    assert _clean_id("") is None
    assert _clean_id("   ") is None
    assert _clean_id("user/123") is None
    assert _clean_id(r"user\123") is None
    assert _clean_id("user\0admin") is None
    assert _clean_id("../user123") is None
    assert _clean_id("a" * 129) is None

    assert _clean_id("valid_user_123") == "valid_user_123"
    assert _clean_id("  valid_user_456  ") == "valid_user_456"
    assert _clean_id("a" * 128) == "a" * 128


def test_clean_counts_edge_cases():
    assert _clean_counts(None) == {}
    assert _clean_counts("invalid") == {}
    assert _clean_counts([1, 2, 3]) == {}
    assert _clean_counts({}) == {}

    # Case normalization and trimming
    assert _clean_counts({" EN ": 5, "pt": 10}) == {"pt": 10, "en": 5}

    # Clamping and non-integer types
    assert _clean_counts({"en": 999999}) == {"en": MAX_COUNT}
    assert _clean_counts({"en": 0, "pt": -5, "es": 2.5, "de": True, "fr": False, "ja": 3}) == {"ja": 3}

    # Bounded to MAX_CODES and sorted by (-count, code)
    overflow = {f"{a}{b}": 10 for a in "ab" for b in "abcdefghijklm"}
    cleaned = _clean_counts(overflow)
    assert len(cleaned) == MAX_CODES
    keys = list(cleaned.keys())
    assert keys == sorted(keys)


def test_clean_sessions_edge_cases():
    assert _clean_sessions(None) == []
    assert _clean_sessions("not a list") == []
    assert _clean_sessions({"en": 1}) == []
    assert _clean_sessions([None, 123, "text", {}]) == []

    # Keeps up to MAX_SESSIONS
    long_list = [{"en": i + 1} for i in range(30)]
    cleaned = _clean_sessions(long_list)
    assert len(cleaned) == MAX_SESSIONS
    assert cleaned[-1] == {"en": 30}


def test_resolve_client_precedence():
    mock_client = SimpleNamespace(name="mock")
    assert _resolve_client(mock_client) is mock_client

    # When None is passed, fallback should not raise
    client = _resolve_client(None)
    # Could be None or db or data plane client, but must not raise


def test_get_live_language_sessions_invalid_uid():
    assert get_live_language_sessions("") == []
    assert get_live_language_sessions("   ") == []
    assert get_live_language_sessions("user/traversal") == []
    assert get_live_language_sessions("../parent") == []


def test_get_live_language_sessions_firestore_exception_resilience():
    class BrokenClient:
        def collection(self, _):
            raise RuntimeError("Firestore down")

    assert get_live_language_sessions("valid_uid", firestore_client=BrokenClient()) == []


def test_get_live_language_sessions_missing_or_empty_snapshot():
    snapshot = SimpleNamespace(exists=False, to_dict=lambda: None)
    reference = SimpleNamespace(get=lambda *_: snapshot)
    client = SimpleNamespace(collection=lambda *_: SimpleNamespace(document=lambda *_: reference))
    assert get_live_language_sessions("valid_uid", firestore_client=client) == []


def test_append_live_language_session_validation():
    assert not append_live_language_session("", {"en": 1})
    assert not append_live_language_session("../traversal", {"en": 1})
    assert not append_live_language_session("valid_uid", {})
    assert not append_live_language_session("valid_uid", {"invalid_code": 1})
    assert not append_live_language_session("valid_uid", {"en": -1})


def test_append_live_language_session_client_failure():
    class BrokenClient:
        def collection(self, _):
            raise ConnectionError("Network failure")

    assert not append_live_language_session("valid_uid", {"en": 1}, firestore_client=BrokenClient())


def test_append_live_language_session_non_transaction_client_fallback():
    written = []
    snapshot = SimpleNamespace(exists=True, to_dict=lambda: {FIELD: [{"pt": 2}]})
    doc_ref = SimpleNamespace(
        get=lambda: snapshot,
        update=lambda data: written.append(data),
    )
    mock_client = SimpleNamespace(
        collection=lambda *_: SimpleNamespace(document=lambda *_: doc_ref),
        transaction=None,
    )

    result = append_live_language_session("uid_1", {"en": 4}, firestore_client=mock_client)
    assert result is True
    assert len(written) == 1
    assert written[0] == {FIELD: [{"pt": 2}, {"en": 4}]}


def test_append_transaction_exception_resilience():
    fn = getattr(_append_transaction, 'to_wrap', _append_transaction)
    # If snapshot get fails inside transaction
    broken_ref = SimpleNamespace(get=lambda **_: (_ for _ in ()).throw(RuntimeError("txn read failed")))
    txn = SimpleNamespace(update=lambda *_: None)
    assert not fn(txn, broken_ref, {"en": 1})

    # If update fails inside transaction
    good_snapshot = SimpleNamespace(exists=True, to_dict=lambda: {FIELD: []})
    good_ref = SimpleNamespace(get=lambda **_: good_snapshot)
    broken_txn = SimpleNamespace(update=lambda *_: (_ for _ in ()).throw(RuntimeError("txn write failed")))
    assert not fn(broken_txn, good_ref, {"en": 1})


def test_invalidate_live_language_sessions_cache():
    # Should not raise for invalid or valid uids
    invalidate_live_language_sessions_cache("")
    invalidate_live_language_sessions_cache("valid_uid")
    invalidate_live_language_sessions_cache("../bad_path")
