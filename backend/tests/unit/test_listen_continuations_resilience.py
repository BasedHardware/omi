"""Hermetic unit tests for listen_continuations resilience and error boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import MagicMock
import pytest

from database.listen_continuations import (
    MAX_ID_LENGTH,
    _align_datetime_tz,
    _clean_id,
    _clean_timeout,
    _normalize_datetime,
    _resolve_client,
    resolve_live_continuation,
)


class FakeDocument:
    def __init__(self, data: Dict[str, Any] | None = None, exists: bool = True) -> None:
        self._data = data or {}
        self.exists = exists

    def get(self, transaction: Any = None) -> FakeDocument:
        return self

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


class FakeDocRef:
    def __init__(self, path: str, store: Dict[str, FakeDocument]) -> None:
        self.path = path
        self.store = store

    def get(self, transaction: Any = None) -> FakeDocument:
        return self.store.get(self.path, FakeDocument(exists=False))

    def update(self, data: Dict[str, Any]) -> None:
        doc = self.store.get(self.path)
        if doc and doc.exists:
            doc._data.update(data)
        else:
            self.store[self.path] = FakeDocument(data, exists=True)

    def collection(self, name: str) -> FakeCollectionRef:
        return FakeCollectionRef(f"{self.path}/{name}", self.store)


class FakeCollectionRef:
    def __init__(self, path: str, store: Dict[str, FakeDocument]) -> None:
        self.path = path
        self.store = store

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(f"{self.path}/{doc_id}", self.store)


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.store: Dict[str, FakeDocument] = {}

    def collection(self, name: str) -> FakeCollectionRef:
        return FakeCollectionRef(name, self.store)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


class FakeTransaction:
    def update(self, doc_ref: Any, data: Dict[str, Any]) -> None:
        doc_ref.update(data)


def test_clean_id_validation():
    assert _clean_id(None) == ""
    assert _clean_id(123) == ""
    assert _clean_id("") == ""
    assert _clean_id("   ") == ""
    assert _clean_id("users/123") == ""
    assert _clean_id(r"users\123") == ""
    assert _clean_id("uid\0null") == ""
    assert _clean_id("../traversal") == ""
    assert _clean_id("u" * (MAX_ID_LENGTH + 1)) == ""

    assert _clean_id("valid-uid-123") == "valid-uid-123"
    assert _clean_id("  valid-uid-456  ") == "valid-uid-456"
    assert _clean_id("u" * MAX_ID_LENGTH) == "u" * MAX_ID_LENGTH


def test_clean_timeout_sanitization():
    assert _clean_timeout(None) == 120
    assert _clean_timeout("not-int") == 120
    assert _clean_timeout(True) == 120
    assert _clean_timeout(False) == 120
    assert _clean_timeout(0) == 120
    assert _clean_timeout(-10) == 120
    assert _clean_timeout(300) == 300


def test_datetime_normalization_and_alignment():
    # Naive gets converted to UTC
    t_naive = datetime(2026, 9, 30, 8, 0)
    norm = _normalize_datetime(t_naive)
    assert norm.tzinfo == timezone.utc

    # Already aware remains aware
    t_aware = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
    assert _normalize_datetime(t_aware) == t_aware

    # Alignment handles naive reference with aware target and vice versa
    aligned1 = _align_datetime_tz(t_naive, t_aware)
    assert aligned1.tzinfo is not None

    aligned2 = _align_datetime_tz(t_aware, t_naive)
    assert aligned2.tzinfo is None


def test_resolve_client_precedence():
    mock_client = MagicMock()
    assert _resolve_client(mock_client) is mock_client


def test_resolve_live_continuation_invalid_inputs():
    client = FakeFirestoreClient()
    now = datetime.now(timezone.utc)

    # Invalid uid
    assert resolve_live_continuation(
        "", "orig", source="mic", device_id="d1", now=now, timeout=120, firestore_client=client
    ) == (None, None)
    # Invalid origin_id
    assert resolve_live_continuation(
        "u1", "", source="mic", device_id="d1", now=now, timeout=120, firestore_client=client
    ) == (None, None)
    # Invalid source
    assert resolve_live_continuation(
        "u1", "orig", source="", device_id="d1", now=now, timeout=120, firestore_client=client
    ) == (None, None)
    # Invalid proposed mapping
    assert resolve_live_continuation("u1", "orig", source="mic", device_id="d1", now=now, timeout=120, proposed="invalid", firestore_client=client) == (None, None)  # type: ignore[arg-type]


def test_resolve_live_continuation_missing_origin_recording():
    client = FakeFirestoreClient()
    now = datetime.now(timezone.utc)
    # Origin document does not exist in store
    adopted, retired = resolve_live_continuation(
        "u1", "orig1", source="mic", device_id="d1", now=now, timeout=120, firestore_client=client
    )
    assert adopted is None
    assert retired is None


def test_resolve_live_continuation_adopt_resumable_proposal():
    client = FakeFirestoreClient()
    now = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)

    # Set up origin recording session
    client.store["users/u1/recording_sessions/orig1"] = FakeDocument(
        {
            "uid": "u1",
            "recording_session_id": "orig1",
        }
    )

    # Set up candidate conversation in progress
    client.store["users/u1/conversations/conv1"] = FakeDocument(
        {
            "status": "in_progress",
            "source": "mic",
            "client_device_id": "dev1",
            "finished_at": now - timedelta(seconds=10),
        }
    )

    proposed = {"conversation_id": "conv1", "recording_session_id": "rec1"}
    adopted, retired = resolve_live_continuation(
        "u1",
        "orig1",
        source="mic",
        device_id="dev1",
        now=now,
        timeout=120,
        proposed=proposed,
        firestore_client=client,
    )

    assert adopted == proposed
    assert retired is None

    # Check that root was updated with live_continuation
    root_data = client.store["users/u1/recording_sessions/orig1"].to_dict()
    assert root_data["live_continuation"] == proposed


def test_resolve_live_continuation_reuse_existing_resumable():
    client = FakeFirestoreClient()
    now = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)

    # Origin session already points to an active conversation
    client.store["users/u1/recording_sessions/orig1"] = FakeDocument(
        {
            "uid": "u1",
            "recording_session_id": "orig1",
            "live_continuation": {"conversation_id": "conv_existing", "recording_session_id": "rec_existing"},
        }
    )

    # That conversation is still resumable
    client.store["users/u1/conversations/conv_existing"] = FakeDocument(
        {
            "status": "in_progress",
            "source": "mic",
            "client_device_id": "dev1",
            "finished_at": now - timedelta(seconds=20),
        }
    )

    adopted, retired = resolve_live_continuation(
        "u1",
        "orig1",
        source="mic",
        device_id="dev1",
        now=now,
        timeout=120,
        firestore_client=client,
    )

    assert adopted == {"conversation_id": "conv_existing", "recording_session_id": "rec_existing"}
    assert retired is None


def test_resolve_live_continuation_retires_expired_continuation():
    client = FakeFirestoreClient()
    now = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)

    # Existing conversation has expired past timeout (gap_splits = True)
    client.store["users/u1/recording_sessions/orig1"] = FakeDocument(
        {
            "uid": "u1",
            "recording_session_id": "orig1",
            "live_continuation": {"conversation_id": "conv_old", "recording_session_id": "rec_old"},
        }
    )
    client.store["users/u1/conversations/conv_old"] = FakeDocument(
        {
            "status": "in_progress",
            "source": "mic",
            "client_device_id": "dev1",
            "is_locked": False,
            "finished_at": now - timedelta(seconds=200),  # > 120s timeout
        }
    )

    # New proposed candidate
    client.store["users/u1/conversations/conv_new"] = FakeDocument(
        {
            "status": "in_progress",
            "source": "mic",
            "client_device_id": "dev1",
            "finished_at": now - timedelta(seconds=15),
        }
    )

    proposed = {"conversation_id": "conv_new", "recording_session_id": "rec_new"}
    adopted, retired = resolve_live_continuation(
        "u1",
        "orig1",
        source="mic",
        device_id="dev1",
        now=now,
        timeout=120,
        proposed=proposed,
        firestore_client=client,
    )

    assert adopted == proposed
    assert retired == {"conversation_id": "conv_old", "recording_session_id": "rec_old"}


def test_resolve_live_continuation_firestore_exception_resilience():
    broken_client = MagicMock()
    broken_client.collection.side_effect = RuntimeError("Firestore unavailable")

    now = datetime.now(timezone.utc)
    adopted, retired = resolve_live_continuation(
        "u1", "orig1", source="mic", device_id="dev1", now=now, timeout=120, firestore_client=broken_client
    )
    assert adopted is None
    assert retired is None


def test_resolve_live_continuation_naive_finished_at_alignment():
    client = FakeFirestoreClient()
    # Aware now
    now = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)

    client.store["users/u1/recording_sessions/orig1"] = FakeDocument(
        {
            "uid": "u1",
            "recording_session_id": "orig1",
            "live_continuation": {"conversation_id": "conv_existing", "recording_session_id": "rec_existing"},
        }
    )

    # Naive finished_at in row (without tzinfo)
    naive_finish = datetime(2026, 9, 30, 9, 59, 40)
    client.store["users/u1/conversations/conv_existing"] = FakeDocument(
        {
            "status": "in_progress",
            "source": "mic",
            "client_device_id": "dev1",
            "finished_at": naive_finish,
        }
    )

    # Must not raise TypeError when subtracting aware now and naive finished_at
    adopted, retired = resolve_live_continuation(
        "u1",
        "orig1",
        source="mic",
        device_id="dev1",
        now=now,
        timeout=120,
        firestore_client=client,
    )

    assert adopted == {"conversation_id": "conv_existing", "recording_session_id": "rec_existing"}
    assert retired is None
