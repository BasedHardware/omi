"""Unit tests verifying defensive resilience and validation in sync_backfill_sequencer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import pytest

from database.sync_backfill_sequencer import (
    begin_job,
    claim_next,
    due_owners,
    due_pending,
    finish_job,
    get_owner,
    is_registered,
    register_job,
    renew_job,
)


class _MockDocRef:
    def __init__(self, data: dict[str, Any] | None = None):
        self.data = data
        self.exists = data is not None

    def get(self, transaction: Any = None) -> Any:
        return self

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self.data) if self.data is not None else None

    def set(self, payload: dict[str, Any], merge: bool = False) -> None:
        if self.data is None or not merge:
            self.data = dict(payload)
        else:
            self.data.update(payload)
        self.exists = True

    def update(self, payload: dict[str, Any]) -> None:
        if self.data is not None:
            self.data.update(payload)

    def delete(self) -> None:
        self.data = None
        self.exists = False


class _MockQuery:
    def __init__(self, items: list[dict[str, Any]] | None = None):
        self._items = items if items is not None else []
        self._limit = 100

    def where(self, *args: Any, **kwargs: Any) -> _MockQuery:
        return self

    def order_by(self, field: str) -> _MockQuery:
        return self

    def limit(self, count: int) -> _MockQuery:
        self._limit = count
        return self

    def stream(self, transaction: Any = None) -> list[Any]:
        class _Doc:
            def __init__(self, data: dict[str, Any]):
                self._data = data
                self.id = data.get("id", "doc-1")
                self.exists = True

            def to_dict(self) -> dict[str, Any]:
                return dict(self._data)

        return [_Doc(d) for d in self._items[:self._limit]]


class _MockTransaction:
    def set(self, doc_ref: _MockDocRef, payload: dict[str, Any], merge: bool = False) -> None:
        doc_ref.set(payload, merge=merge)

    def update(self, doc_ref: _MockDocRef, payload: dict[str, Any]) -> None:
        doc_ref.update(payload)

    def delete(self, doc_ref: _MockDocRef) -> None:
        doc_ref.delete()


class _MockClient:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, _MockDocRef]] = {}

    def collection(self, name: str) -> Any:
        self.collections.setdefault(name, {})
        client = self

        class _Col:
            def document(self, doc_id: str) -> _MockDocRef:
                if doc_id not in client.collections[name]:
                    client.collections[name][doc_id] = _MockDocRef(None)
                return client.collections[name][doc_id]

            def where(self, *args: Any, **kwargs: Any) -> _MockQuery:
                items = [ref.data for ref in client.collections[name].values() if ref.data is not None]
                return _MockQuery(items)

        return _Col()

    def transaction(self) -> Any:
        return _MockTransaction()


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMI_ENV_STAGE", "prod")
    monkeypatch.setattr("google.cloud.firestore.transactional", lambda fn: fn)


def test_register_job_validates_inputs() -> None:
    """Verify register_job validates uid, job_id, and payload dictionary."""
    mock_client = _MockClient()
    with pytest.raises(ValueError, match="uid must be a non-empty string without slashes"):
        register_job("", "job-1", {}, None, firestore_client=mock_client)

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        register_job("u1", "bad/job", {}, None, firestore_client=mock_client)

    with pytest.raises(ValueError, match="payload must be a dictionary"):
        register_job("u1", "job-1", "not-dict", None, firestore_client=mock_client)  # type: ignore[arg-type]


def test_register_job_normalizes_and_registers() -> None:
    """Verify register_job registers pending job doc in Firestore."""
    mock_client = _MockClient()
    created = register_job("  u-test  ", "  job-abc  ", {"key": "val"}, 1700000000.0, firestore_client=mock_client)
    assert created is True

    # Re-registering existing job returns False
    second = register_job("u-test", "job-abc", {"key": "val"}, 1700000000.0, firestore_client=mock_client)
    assert second is False


def test_due_pending_and_due_owners_limit_validation() -> None:
    """Verify due_pending and due_owners strictly validate limit and clamp."""
    mock_client = _MockClient()

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        due_pending(limit=0, firestore_client=mock_client)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        due_pending(limit=True, firestore_client=mock_client)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        due_owners(limit=-1, firestore_client=mock_client)


def test_begin_renew_finish_job_validates_inputs() -> None:
    """Verify begin_job, renew_job, finish_job validate uid, job_id, and epoch."""
    mock_client = _MockClient()

    with pytest.raises(ValueError, match="uid must be a non-empty string without slashes"):
        begin_job("", "job-1", 1, firestore_client=mock_client)

    with pytest.raises(ValueError, match="epoch must be a non-negative integer"):
        renew_job("u1", "job-1", -1, firestore_client=mock_client)

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        finish_job("u1", "job/bad", 1, "success", firestore_client=mock_client)


def test_is_registered_and_get_owner_validation() -> None:
    """Verify is_registered and get_owner validate inputs."""
    mock_client = _MockClient()

    with pytest.raises(ValueError, match="uid must be a non-empty string without slashes"):
        is_registered("", "job-1", firestore_client=mock_client)

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        is_registered("u1", "", firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid must be a non-empty string without slashes"):
        get_owner("bad/uid", firestore_client=mock_client)
