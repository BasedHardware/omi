from datetime import datetime, timezone

import pytest

import database.memory_imports as memory_imports_db
from database.memory_imports import ingest_memory_import_batch
from models.memory_imports import MemoryImportBatchItem, MemoryImportBatchRequest
from utils.memory.import_write_guard import import_write_block_mode, import_write_violation


class _AlreadyExists(Exception):
    pass


class _Conflict(Exception):
    pass


@pytest.fixture(autouse=True)
def _patch_memory_imports_firestore(monkeypatch):
    monkeypatch.setattr(memory_imports_db, "AlreadyExists", _AlreadyExists)
    monkeypatch.setattr(memory_imports_db, "Conflict", _Conflict)
    monkeypatch.setattr(memory_imports_db, "_firestore_increment", lambda value: ("__increment__", value))


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _FakeDocRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def get(self):
        return _FakeSnapshot(self._db.docs.get(self._path))

    def create(self, data):
        if self._path in self._db.docs:
            raise _AlreadyExists()
        self._db.docs[self._path] = dict(data)

    def set(self, data, merge=False):
        data = self._db.apply_increment_sentinels(self._path, data)
        if merge and self._path in self._db.docs:
            next_data = dict(self._db.docs[self._path])
            next_data.update(data)
            self._db.docs[self._path] = next_data
            return
        self._db.docs[self._path] = dict(data)


class _FakeDb:
    def __init__(self):
        self.docs = {}

    def document(self, path):
        return _FakeDocRef(self, path)

    def apply_increment_sentinels(self, path, data):
        next_data = dict(data)
        current = self.docs.get(path, {})
        for key, value in list(next_data.items()):
            if isinstance(value, tuple) and value[0] == "__increment__":
                next_data[key] = int(current.get(key) or 0) + value[1]
        return next_data


def test_import_ingest_writes_artifacts_not_product_memories():
    db = _FakeDb()
    request = MemoryImportBatchRequest(
        source_type="gmail",
        import_run_id="run-gmail-1",
        items=[
            MemoryImportBatchItem(
                external_id="message-1",
                occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
                title="Project update",
                snippet="The user is working on Omi memory imports.",
                content="The user is working on Omi memory imports.",
                metadata={"import_kind": "email"},
            )
        ],
    )

    result = ingest_memory_import_batch("uid-1", request, db_client=db)

    assert result.response.run_id == "run-gmail-1"
    assert result.response.artifacts_received == 1
    assert result.response.artifacts_created == 1
    assert result.response.artifacts_deduped == 0
    assert any(path.startswith("users/uid-1/memory_import_artifacts/") for path in db.docs)
    artifact_path = next(path for path in db.docs if path.startswith("users/uid-1/memory_import_artifacts/"))
    assert db.docs[artifact_path]["redacted_body"] is None
    assert db.docs[artifact_path]["redaction_status"] == "title_snippet_only"
    assert db.docs["users/uid-1/memory_import_runs/run-gmail-1"]["artifact_count"] == 1
    assert not any("/memory_items/" in path for path in db.docs)
    assert not any("/memories/" in path for path in db.docs)


def test_import_ingest_is_idempotent_by_external_id():
    db = _FakeDb()
    request = MemoryImportBatchRequest(
        source_type="apple-notes",
        import_run_id="run-notes-1",
        items=[MemoryImportBatchItem(external_id="note-1", title="One", content="One")],
    )

    first = ingest_memory_import_batch("uid-1", request, db_client=db)
    second = ingest_memory_import_batch("uid-1", request, db_client=db)

    artifact_paths = [path for path in db.docs if path.startswith("users/uid-1/memory_import_artifacts/")]
    assert len(artifact_paths) == 1
    assert first.response.artifacts_created == 1
    assert second.response.artifacts_created == 0
    assert second.response.artifacts_deduped == 1
    assert db.docs["users/uid-1/memory_import_runs/run-notes-1"]["artifact_count"] == 1
    assert db.docs["users/uid-1/memory_import_runs/run-notes-1"]["deduped_count"] == 1


def test_import_ingest_artifact_id_uses_content_hash_with_external_id():
    db = _FakeDb()
    first = MemoryImportBatchRequest(
        source_type="gmail",
        import_run_id="run-gmail-1",
        items=[MemoryImportBatchItem(external_id="message-1", title="One", content="One")],
    )
    second = MemoryImportBatchRequest(
        source_type="gmail",
        import_run_id="run-gmail-1",
        items=[MemoryImportBatchItem(external_id="message-1", title="Two", content="Two")],
    )

    ingest_memory_import_batch("uid-1", first, db_client=db)
    ingest_memory_import_batch("uid-1", second, db_client=db)

    artifact_paths = [path for path in db.docs if path.startswith("users/uid-1/memory_import_artifacts/")]
    assert len(artifact_paths) == 2


def test_import_ingest_can_store_full_body_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("MEMORY_IMPORT_BODY_STORAGE_MODE", "full")
    db = _FakeDb()
    request = MemoryImportBatchRequest(
        source_type="gmail",
        import_run_id="run-gmail-1",
        items=[MemoryImportBatchItem(external_id="message-1", title="One", snippet="Short", content="Full body")],
    )

    ingest_memory_import_batch("uid-1", request, db_client=db)

    artifact_path = next(path for path in db.docs if path.startswith("users/uid-1/memory_import_artifacts/"))
    assert db.docs[artifact_path]["redacted_body"] == "Full body"
    assert db.docs[artifact_path]["redaction_status"] == "importer_full_excerpt"


def test_import_run_id_is_safe_for_firestore_document_path():
    db = _FakeDb()
    request = MemoryImportBatchRequest(
        source_type="gmail",
        import_run_id="folder/run-1",
        items=[MemoryImportBatchItem(external_id="message-1", title="One", content="One")],
    )

    result = ingest_memory_import_batch("uid-1", request, db_client=db)

    assert "/" not in result.response.run_id
    assert f"users/uid-1/memory_import_runs/{result.response.run_id}" in db.docs


def test_import_write_guard_detects_source_and_tags_from_raw_payload():
    assert import_write_violation({"source": "gmail"}) == {"source": "gmail"}
    assert import_write_violation({"tags": ["Apple Notes"], "metadata": {"import_kind": "profile"}}) == {
        "tags": ["apple_notes"]
    }
    assert import_write_violation({"tags": ["Calendar"]}) is None
    assert import_write_violation({"tags": ["Import"]}) is None
    assert import_write_violation({"content": "actual manual memory", "tags": ["manual"]}) is None


def test_import_write_block_mode_defaults_and_sanitizes(monkeypatch):
    monkeypatch.delenv("MEMORY_IMPORT_WRITE_BLOCK_MODE", raising=False)
    assert import_write_block_mode() == "log"
    monkeypatch.setenv("MEMORY_IMPORT_WRITE_BLOCK_MODE", "enforce")
    assert import_write_block_mode() == "enforce"
    monkeypatch.setenv("MEMORY_IMPORT_WRITE_BLOCK_MODE", "surprise")
    assert import_write_block_mode() == "log"
