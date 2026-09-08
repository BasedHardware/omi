from datetime import datetime, timedelta, timezone

from database import frame_requests


class _Snapshot:
    def __init__(self, document):
        self.id = document.id
        self.reference = document

    def to_dict(self):
        return dict(self.reference.data)


class _Document:
    def __init__(self, document_id):
        self.id = document_id
        self.data = {}
        self.children = {}

    def collection(self, name):
        return self.children.setdefault(name, _Collection())

    def set(self, data, merge=False):
        self.data = {**self.data, **data} if merge else dict(data)

    def update(self, data):
        self.data.update(data)

    def delete(self):
        self.data.clear()


class _Collection:
    def __init__(self):
        self.documents = {}
        self.maximum = 1000

    def document(self, document_id):
        return self.documents.setdefault(document_id, _Document(document_id))

    def where(self, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, maximum):
        self.maximum = maximum
        return self

    def stream(self):
        rows = [document for document in self.documents.values() if document.data]
        return iter(_Snapshot(document) for document in rows[: self.maximum])


class _Client:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _Collection())


def test_conversation_deletion_outbox_retries_storage_failures_until_acknowledged():
    client = _Client()
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    frame_requests.persist_conversation_frame_deletion_outbox(
        "uid-1", "conversation-1", ["permanent-a", "permanent-b"], now=now, firestore_client=client
    )
    failures = {"permanent-a"}
    deleted = []

    def delete_storage(storage_id):
        if storage_id in failures:
            raise RuntimeError("storage outage")
        deleted.append(storage_id)

    assert (
        frame_requests.cleanup_conversation_frame_deletion_outbox(
            "uid-1", delete_storage=delete_storage, now=now, firestore_client=client
        )
        == 1
    )
    assert deleted == ["permanent-b"]

    failures.clear()
    assert (
        frame_requests.cleanup_conversation_frame_deletion_outbox(
            "uid-1", delete_storage=delete_storage, now=now + timedelta(seconds=2), firestore_client=client
        )
        == 1
    )
    assert deleted == ["permanent-b", "permanent-a"]
    outbox = client.collection("users").document("uid-1").collection(frame_requests.FRAME_DELETION_OUTBOX_COLLECTION)
    assert not any(document.data for document in outbox.documents.values())
