import sys
from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import AutoMockModule

for mod in [
    "google",
    "google.cloud",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
]:
    if mod not in sys.modules:
        sys.modules[mod] = AutoMockModule(mod)

# Ensure transactional decorator passes through callable
sys.modules["google.cloud.firestore"].transactional = lambda fn: fn
if hasattr(sys.modules["google.cloud"], "firestore"):
    sys.modules["google.cloud"].firestore.transactional = lambda fn: fn

import database._client as client_mod
client_mod.run_transactional = lambda client, fn, *args, **kwargs: fn(
    client.transaction() if hasattr(client, "transaction") else None, *args, **kwargs
)


from database.import_jobs import (
    _clean_optional_id,
    _sanitize_id,
    cancel_import_job_if_active,
    create_import_job,
    delete_import_job,
    get_import_job,
    get_import_jobs,
    update_import_job,
    update_import_job_progress,
    update_import_job_unless_cancelled,
)


class MockDocSnapshot:
    def __init__(self, doc_id, data=None, exists=True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class NotFound(Exception):
    pass


class MockDocRef:
    def __init__(self, doc_id, data=None, exists=True, raise_on_get=False, not_found=False):
        self.id = doc_id
        self.data = data
        self.exists = exists
        self.raise_on_get = raise_on_get
        self.not_found = not_found

    def get(self, transaction=None):
        if self.raise_on_get:
            raise RuntimeError("Store read error")
        return MockDocSnapshot(self.id, self.data, exists=self.exists)

    def set(self, data):
        self.data = dict(data)
        self.exists = True

    def update(self, updates):
        if self.not_found:
            raise NotFound("Document not found")
        if not self.exists:
            raise NotFound("Document not found")
        if self.data is None:
            self.data = {}
        self.data.update(updates)

    def delete(self):
        if self.not_found or not self.exists:
            raise NotFound("Document not found")
        self.exists = False
        self.data = None



class MockTransaction:
    def update(self, ref, updates):
        ref.update(updates)


class MockQuery:
    def __init__(self, docs, raise_on_stream=False):
        self._docs = docs
        self.raise_on_stream = raise_on_stream
        self.last_limit = None

    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, limit_val):
        self.last_limit = limit_val
        return self

    def stream(self):
        if self.raise_on_stream:
            raise RuntimeError("Stream broken")
        return iter(self._docs)


class MockCollection:
    def __init__(self):
        self.docs = {}
        self.raise_on_stream = False

    def document(self, doc_id):
        if doc_id not in self.docs:
            self.docs[doc_id] = MockDocRef(doc_id, exists=False)
        return self.docs[doc_id]

    def where(self, *args, **kwargs):
        docs = [MockDocSnapshot(d.id, d.data, exists=d.exists) for d in self.docs.values() if d.exists]
        return MockQuery(docs, raise_on_stream=self.raise_on_stream)


class MockFirestoreClient:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection()
        return self.collections[name]

    def transaction(self):
        return MockTransaction()


# 1. _sanitize_id tests
def test_sanitize_id_valid():
    assert _sanitize_id("job_123") == "job_123"
    assert _sanitize_id("  job_abc  ") == "job_abc"


def test_sanitize_id_invalid_type_or_empty():
    with pytest.raises(ValueError):
        _sanitize_id(None)
    with pytest.raises(ValueError):
        _sanitize_id("")
    with pytest.raises(ValueError):
        _sanitize_id("   ")


def test_sanitize_id_path_traversal_or_control():
    with pytest.raises(ValueError):
        _sanitize_id("../bad")
    with pytest.raises(ValueError):
        _sanitize_id("a/b")
    with pytest.raises(ValueError):
        _sanitize_id("a\x00b")


# 2. _clean_optional_id tests
def test_clean_optional_id():
    assert _clean_optional_id("job_xyz") == "job_xyz"
    assert _clean_optional_id("  job_xyz  ") == "job_xyz"
    assert _clean_optional_id(None) is None
    assert _clean_optional_id("") is None
    assert _clean_optional_id("../traversal") is None


# 3. create_import_job tests
def test_create_import_job_success():
    client = MockFirestoreClient()
    job_data = {"id": "job-1", "uid": "user-1", "status": "pending"}
    job_id = create_import_job(job_data, firestore_client=client)
    assert job_id == "job-1"
    assert client.collection("import_jobs").document("job-1").data == job_data


def test_create_import_job_invalid_id():
    client = MockFirestoreClient()
    with pytest.raises(ValueError):
        create_import_job({"id": "", "uid": "user-1"}, firestore_client=client)
    with pytest.raises(ValueError):
        create_import_job({"id": "../bad", "uid": "user-1"}, firestore_client=client)


# 4. update_import_job tests
def test_update_import_job_success():
    client = MockFirestoreClient()
    client.collection("import_jobs").document("job-1").set({"status": "pending"})
    res = update_import_job("job-1", {"status": "processing"}, firestore_client=client)
    assert res is True
    assert client.collection("import_jobs").document("job-1").data["status"] == "processing"


def test_update_import_job_empty_updates():
    client = MockFirestoreClient()
    res = update_import_job("job-1", {}, firestore_client=client)
    assert res is False


def test_update_import_job_not_found():
    client = MockFirestoreClient()
    doc_ref = client.collection("import_jobs").document("job-missing")
    doc_ref.not_found = True
    res = update_import_job("job-missing", {"status": "processing"}, firestore_client=client)
    assert res is False


# 5. update_import_job_unless_cancelled tests
def test_update_import_job_unless_cancelled_success():
    client = MockFirestoreClient()
    client.collection("import_jobs").document("job-1").set({"status": "processing"})
    res = update_import_job_unless_cancelled("job-1", {"progress": 50}, firestore_client=client)
    assert res is True
    assert client.collection("import_jobs").document("job-1").data["progress"] == 50


def test_update_import_job_unless_cancelled_when_cancelled():
    client = MockFirestoreClient()
    client.collection("import_jobs").document("job-1").set({"status": "cancelled"})
    res = update_import_job_unless_cancelled("job-1", {"progress": 50}, firestore_client=client)
    assert res is False


# 6. cancel_import_job_if_active tests
def test_cancel_import_job_if_active_pending():
    client = MockFirestoreClient()
    client.collection("import_jobs").document("job-1").set({"status": "pending"})
    res = cancel_import_job_if_active("job-1", firestore_client=client)
    assert res is True
    doc = client.collection("import_jobs").document("job-1").data
    assert doc["status"] == "cancelled"
    assert doc["error"] == "Cancelled by user"


def test_cancel_import_job_if_active_already_cancelled():
    client = MockFirestoreClient()
    client.collection("import_jobs").document("job-1").set({"status": "cancelled"})
    res = cancel_import_job_if_active("job-1", firestore_client=client)
    assert res is False


def test_cancel_import_job_if_active_invalid_id():
    client = MockFirestoreClient()
    assert cancel_import_job_if_active("   ", firestore_client=client) is False


# 7. update_import_job_progress tests
def test_update_import_job_progress_success():
    client = MockFirestoreClient()
    client.collection("import_jobs").document("job-1").set({"processed_files": 1})
    res = update_import_job_progress("job-1", {"processed_files": 2}, firestore_client=client)
    assert res is True
    assert client.collection("import_jobs").document("job-1").data["processed_files"] == 2


def test_update_import_job_progress_unexpected_field():
    client = MockFirestoreClient()
    with pytest.raises(ValueError, match="not import job progress fields"):
        update_import_job_progress("job-1", {"status": "done"}, firestore_client=client)


# 8. get_import_job tests
def test_get_import_job_hydrates_missing_id():
    client = MockFirestoreClient()
    client.collection("import_jobs").document("job-legacy").set({"status": "completed"})
    job = get_import_job("job-legacy", firestore_client=client)
    assert job is not None
    assert job["id"] == "job-legacy"
    assert job["status"] == "completed"


def test_get_import_job_error_boundary():
    client = MockFirestoreClient()
    doc_ref = client.collection("import_jobs").document("job-err")
    doc_ref.raise_on_get = True
    assert get_import_job("job-err", firestore_client=client) is None


# 9. get_import_jobs tests
def test_get_import_jobs_limit_clamped():
    client = MockFirestoreClient()
    client.collection("import_jobs").document("j1").set({"uid": "u1", "created_at": 100})
    jobs = get_import_jobs("u1", limit=-10, firestore_client=client)
    assert len(jobs) == 1
    assert jobs[0]["id"] == "j1"

    jobs_high = get_import_jobs("u1", limit=99999, firestore_client=client)
    assert len(jobs_high) == 1


def test_get_import_jobs_error_boundary():
    client = MockFirestoreClient()
    client.collection("import_jobs").raise_on_stream = True
    assert get_import_jobs("u1", firestore_client=client) == []


# 10. delete_import_job tests
def test_delete_import_job_success():
    client = MockFirestoreClient()
    client.collection("import_jobs").document("job-1").set({"status": "pending"})
    res = delete_import_job("job-1", firestore_client=client)
    assert res is True
    assert client.collection("import_jobs").document("job-1").exists is False


def test_delete_import_job_not_found():
    client = MockFirestoreClient()
    doc_ref = client.collection("import_jobs").document("job-del")
    doc_ref.not_found = True
    assert delete_import_job("job-del", firestore_client=client) is False
