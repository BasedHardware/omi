"""Hermetic resilience unit tests for database.import_jobs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from database.import_jobs import (
    MAX_ID_LENGTH,
    _clean_id,
    _resolve_client,
    create_import_job,
    delete_import_job,
    get_import_job,
    get_import_jobs,
    update_import_job,
)


class FakeDocSnapshot:

    def __init__(self, exists: bool = True, data: Optional[Dict[str, Any]] = None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        return self._data


class FakeDocRef:

    def __init__(self, doc_id: str, store: Optional[Dict[str, Dict[str, Any]]] = None):
        self.doc_id = doc_id
        self.store = store if store is not None else {}
        self.deleted = False

    def get(self) -> FakeDocSnapshot:
        if self.doc_id in self.store and not self.deleted:
            return FakeDocSnapshot(exists=True, data=self.store[self.doc_id])
        return FakeDocSnapshot(exists=False, data=None)

    def set(self, data: Dict[str, Any]) -> None:
        self.store[self.doc_id] = data

    def update(self, updates: Dict[str, Any]) -> None:
        if self.doc_id not in self.store or self.deleted:
            raise Exception("Document not found")
        self.store[self.doc_id].update(updates)

    def delete(self) -> None:
        self.deleted = True
        self.store.pop(self.doc_id, None)


class FakeQuery:

    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs
        self._limit: Optional[int] = None
        self._filters: List[Any] = []

    def where(self, filter: Optional[Any] = None) -> FakeQuery:
        if filter:
            self._filters.append(filter)
        return self

    def order_by(self, field: str, direction: Optional[str] = None) -> FakeQuery:
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def stream(self) -> List[FakeDocSnapshot]:
        results = []
        for d in self.docs:
            match = True
            for f in self._filters:
                op = getattr(f, "op_string", getattr(f, "op", "=="))
                field = getattr(f, "field_path", getattr(f, "field", ""))
                val = getattr(f, "value", None)
                if op == "==" and d.get(field) != val:
                    match = False
                    break
            if match:
                results.append(FakeDocSnapshot(exists=True, data=d))
        if self._limit is not None:
            results = results[: self._limit]
        return results


class FakeCollection:

    def __init__(self, store: Optional[Dict[str, Dict[str, Any]]] = None):
        self.store = store if store is not None else {}

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(doc_id, self.store)

    def where(self, filter: Optional[Any] = None) -> FakeQuery:
        docs = list(self.store.values())
        q = FakeQuery(docs)
        return q.where(filter)


class FakeFirestoreClient:

    def __init__(self):
        self.store: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def collection(self, name: str) -> FakeCollection:
        if name not in self.store:
            self.store[name] = {}
        return FakeCollection(self.store[name])


# --- Test Cases ---


def test_clean_id_validates_and_normalizes():
    assert _clean_id("user_123") == "user_123"
    assert _clean_id("  job_abc-456  ") == "job_abc-456"
    assert _clean_id("") == ""
    assert _clean_id("   ") == ""
    assert _clean_id(None) == ""
    assert _clean_id(12345) == ""  # type: ignore[arg-type]
    # Path traversal rejection
    assert _clean_id("../evil") == ""
    assert _clean_id("dir/job_1") == ""
    assert _clean_id("dir\\job_2") == ""
    assert _clean_id("job\x00null") == ""
    # Length bound
    assert _clean_id("a" * (MAX_ID_LENGTH + 1)) == ""
    assert _clean_id("a" * MAX_ID_LENGTH) == "a" * MAX_ID_LENGTH


def test_create_import_job_valid_flow():
    client = FakeFirestoreClient()
    job_data = {"id": "job_001", "uid": "user_abc", "status": "pending", "type": "gdrive"}
    res = create_import_job(job_data, client=client)
    assert res == "job_001"
    saved = client.collection("import_jobs").document("job_001").get().to_dict()
    assert saved["id"] == "job_001"
    assert saved["status"] == "pending"


def test_create_import_job_rejects_missing_or_invalid_id():
    client = FakeFirestoreClient()
    with pytest.raises(ValueError, match="job_data must be a dictionary"):
        create_import_job("not a dict", client=client)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Invalid or missing 'id'"):
        create_import_job({}, client=client)
    with pytest.raises(ValueError, match="Invalid or missing 'id'"):
        create_import_job({"id": ""}, client=client)
    with pytest.raises(ValueError, match="Invalid or missing 'id'"):
        create_import_job({"id": "../malicious"}, client=client)
    for bad_uid in ["", "   ", "../bad", "dir/uid", "a" * (MAX_ID_LENGTH + 1)]:
        with pytest.raises(ValueError, match="Invalid or missing 'uid'"):
            create_import_job({"id": "valid_job", "uid": bad_uid}, client=client)


def test_create_import_job_handles_transport_error():
    client = MagicMock()
    client.collection.side_effect = Exception("Firestore network timeout")
    with pytest.raises(Exception, match="Firestore network timeout"):
        create_import_job({"id": "job_err"}, client=client)


def test_update_import_job_valid_flow():
    client = FakeFirestoreClient()
    create_import_job({"id": "job_100", "status": "pending"}, client=client)
    success = update_import_job("job_100", {"status": "completed", "total_files": 12}, client=client)
    assert success is True
    updated = get_import_job("job_100", client=client)
    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["total_files"] == 12


def test_update_import_job_invalid_id_or_empty_updates():
    client = FakeFirestoreClient()
    assert update_import_job("", {"status": "failed"}, client=client) is False
    assert update_import_job("../bad", {"status": "failed"}, client=client) is False
    assert update_import_job(None, {"status": "failed"}, client=client) is False  # type: ignore[arg-type]
    assert update_import_job("job_1", "not_a_dict", client=client) is False  # type: ignore[arg-type]
    assert update_import_job("job_1", {}, client=client) is True


def test_update_import_job_handles_firestore_error():
    client = FakeFirestoreClient()
    with pytest.raises(Exception, match="Document not found"):
        update_import_job("nonexistent_job", {"status": "failed"}, client=client)


def test_get_import_job_valid_and_missing():
    client = FakeFirestoreClient()
    create_import_job({"id": "job_200", "uid": "u1", "status": "running"}, client=client)
    doc = get_import_job("job_200", client=client)
    assert doc is not None
    assert doc["id"] == "job_200"
    assert get_import_job("job_nonexistent", client=client) is None


def test_get_import_job_invalid_id_short_circuits():
    client = MagicMock()
    assert get_import_job("", client=client) is None
    assert get_import_job("../traversal", client=client) is None
    assert get_import_job(None, client=client) is None  # type: ignore[arg-type]
    client.collection.assert_not_called()


def test_get_import_job_handles_transport_error():
    client = MagicMock()
    client.collection.side_effect = Exception("Firestore unavailable")
    assert get_import_job("job_err", client=client) is None


def test_get_import_jobs_filters_and_boundary_clamping():
    client = FakeFirestoreClient()
    for i in range(10):
        create_import_job({"id": f"job_{i}", "uid": "target_user", "created_at": i}, client=client)
    create_import_job({"id": "other_job", "uid": "other_user", "created_at": 1}, client=client)

    # Standard query
    jobs = get_import_jobs("target_user", limit=5, client=client)
    assert len(jobs) == 5
    assert all(j["uid"] == "target_user" for j in jobs)

    # Clamping negative limit -> clamps to 1
    jobs_neg = get_import_jobs("target_user", limit=-10, client=client)
    assert len(jobs_neg) == 1

    # Clamping zero limit -> clamps to 1
    jobs_zero = get_import_jobs("target_user", limit=0, client=client)
    assert len(jobs_zero) == 1

    # Clamping excessive limit -> clamps to MAX_IMPORT_JOBS_LIMIT (1000)
    jobs_high = get_import_jobs("target_user", limit=999999, client=client)
    assert len(jobs_high) == 10


def test_get_import_jobs_invalid_uid_returns_empty():
    client = MagicMock()
    assert get_import_jobs("", client=client) == []
    assert get_import_jobs("   ", client=client) == []
    assert get_import_jobs(None, client=client) == []  # type: ignore[arg-type]
    assert get_import_jobs("../traversal", client=client) == []
    client.collection.assert_not_called()


def test_get_import_jobs_handles_query_stream_error():
    client = MagicMock()
    client.collection.side_effect = Exception("Index building in progress")
    assert get_import_jobs("u1", client=client) == []


def test_delete_import_job_valid_and_invalid():
    client = FakeFirestoreClient()
    create_import_job({"id": "job_to_del", "uid": "u1"}, client=client)
    assert get_import_job("job_to_del", client=client) is not None
    assert delete_import_job("job_to_del", client=client) is True
    assert get_import_job("job_to_del", client=client) is None

    # Invalid id
    assert delete_import_job("", client=client) is False
    assert delete_import_job(None, client=client) is False  # type: ignore[arg-type]
    assert delete_import_job("../bad", client=client) is False


def test_delete_import_job_handles_transport_error():
    client = MagicMock()
    client.collection.side_effect = Exception("Firestore error")
    with pytest.raises(Exception, match="Firestore error"):
        delete_import_job("job_err", client=client)


def test_resolve_client_fallback():
    mock_custom = MagicMock()
    assert _resolve_client(mock_custom) is mock_custom
