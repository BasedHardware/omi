import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from database import frame_requests


class _Snapshot:
    def __init__(self, reference):
        self.reference = reference
        self.id = reference.id

    @property
    def exists(self):
        return self.reference.exists

    def to_dict(self):
        return dict(self.reference.row) if self.exists else None


class _Reference:
    def __init__(self, document_id, row=None, *, path_prefix="users/uid-1"):
        self.id = document_id
        self.row = dict(row or {})
        self.exists = row is not None
        self.path = f"{path_prefix}/{document_id}"

    def get(self, transaction=None):
        return _Snapshot(self)

    def update(self, values):
        for key, value in values.items():
            if value is frame_requests.firestore.DELETE_FIELD:
                self.row.pop(key, None)
            else:
                self.row[key] = value

    def delete(self):
        self.exists = False
        self.row = {}


class _Query:
    def __init__(self, collection, predicate):
        self.collection = collection
        self.predicate = predicate
        self.page_size = 10_000

    def where(self, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self.page_size = value
        return self

    def stream(self):
        rows = [ref for ref in self.collection.rows.values() if ref.exists and self.predicate(ref.row)]
        rows.sort(key=lambda ref: ref.row.get("output_expires_at") or ref.row.get("expires_at"))
        return iter(_Snapshot(ref) for ref in rows[: self.page_size])


class _Collection:
    def __init__(self, name):
        self.name = name
        self.rows = {}

    def document(self, document_id):
        return self.rows.setdefault(
            document_id,
            _Reference(document_id, path_prefix=f"users/uid-1/{self.name}"),
        )


class _UserDocument:
    def __init__(self, client):
        self.client = client

    def collection(self, name):
        return self.client.collections.setdefault(name, _Collection(name))


class _UsersCollection:
    def __init__(self, client):
        self.client = client

    def document(self, _uid):
        return _UserDocument(self.client)


class _Transaction:
    @staticmethod
    def create(reference, values):
        if reference.exists:
            raise RuntimeError("already exists")
        reference.row = dict(values)
        reference.exists = True

    @staticmethod
    def update(reference, values):
        reference.update(values)

    @staticmethod
    def delete(reference):
        reference.delete()


class _Client:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        assert name == "users"
        return _UsersCollection(self)

    def transaction(self):
        return _Transaction()


class _Spec:
    def __init__(self, predicate_factory):
        self.predicate_factory = predicate_factory

    def build(self, collection, values, **_kwargs):
        return _Query(collection, self.predicate_factory(values))


@pytest.fixture(autouse=True)
def _plain_transactions(monkeypatch):
    monkeypatch.setattr(frame_requests.firestore, "transactional", lambda function: function)


def test_expired_vision_output_is_stripped_but_paid_tombstone_never_expires(monkeypatch):
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    client = _Client()
    authority_key = "stable-session-turn"
    receipt_id = hashlib.sha256(authority_key.encode("utf-8")).hexdigest()
    receipt = _Reference(
        receipt_id,
        {
            "request_id": "frame-1",
            "account_generation": 7,
            "state": "invoked",
            "created_at": now,
            "lease_expires_at": now + timedelta(minutes=5),
        },
        path_prefix="users/uid-1/frame_vision_receipts",
    )
    client.collections[frame_requests.FRAME_VISION_RECEIPTS_COLLECTION] = _Collection(
        frame_requests.FRAME_VISION_RECEIPTS_COLLECTION
    )
    client.collections[frame_requests.FRAME_VISION_RECEIPTS_COLLECTION].rows[receipt_id] = receipt
    monkeypatch.setattr(
        frame_requests,
        "FRAME_VISION_OUTPUT_EXPIRY_QUERY",
        _Spec(lambda values: lambda row: row.get("output_expires_at", now + timedelta(days=99)) <= values["now"]),
    )

    frame_requests.complete_frame_vision_invocation(
        "uid-1",
        authority_key,
        request_id="frame-1",
        account_generation=7,
        description="derived private description",
        now=now,
        firestore_client=client,
    )
    assert receipt.row["output_expires_at"] == now + timedelta(seconds=frame_requests.FRAME_REQUEST_MAX_TTL_SECONDS)
    assert receipt.row["output_expires_at"] <= now + timedelta(days=7)

    page = frame_requests.cleanup_expired_frame_vision_outputs(
        "uid-1",
        now=now + timedelta(days=8),
        limit=1,
        firestore_client=client,
        report_page=True,
    )

    assert page == frame_requests.FrameCleanupPage(processed=1, cleaned=1)
    assert receipt.exists is True
    assert receipt.row["state"] == "payload_expired"
    assert "description" not in receipt.row
    assert "completed_at" not in receipt.row
    assert "output_expires_at" not in receipt.row
    same_request = frame_requests.reserve_frame_vision_invocation(
        "uid-1",
        authority_key,
        request_id="frame-1",
        account_generation=7,
        firestore_client=client,
    )
    assert same_request["state"] == "payload_expired"
    assert same_request.get("reserved") is not True
    with pytest.raises(PermissionError):
        frame_requests.reserve_frame_vision_invocation(
            "uid-1",
            authority_key,
            request_id="frame-2",
            account_generation=7,
            firestore_client=client,
        )


def test_terminal_metadata_cleanup_pages_without_touching_pending_or_attached(monkeypatch):
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    client = _Client()
    collection = _Collection(frame_requests.FRAME_REQUESTS_COLLECTION)
    client.collections[frame_requests.FRAME_REQUESTS_COLLECTION] = collection

    def add(document_id, *, state="pruned", cleanup_state="not_required", expires_at=None):
        collection.rows[document_id] = _Reference(
            document_id,
            {
                "state": state,
                "cleanup_state": cleanup_state,
                "expires_at": expires_at or now - timedelta(days=1),
            },
            path_prefix="users/uid-1/frame_requests",
        )

    for index in range(5):
        add(f"expired-{index}", cleanup_state="deleted" if index % 2 else "not_required")
    add("gcs-failure", cleanup_state="failed")
    add("attached", state="attached", cleanup_state="permanent")
    add("future", expires_at=now + timedelta(days=1))
    terminal = {state.value for state in frame_requests.TERMINAL_FRAME_REQUEST_STATES if state.value != "attached"}
    safe_cleanup = {"not_required", "deleted"}
    monkeypatch.setattr(
        frame_requests,
        "FRAME_REQUEST_METADATA_EXPIRY_QUERY",
        _Spec(
            lambda values: lambda row: row.get("state") in terminal
            and row.get("cleanup_state") in safe_cleanup
            and row.get("expires_at") <= values["now"]
        ),
    )

    pages = [
        frame_requests.delete_expired_frame_request_metadata(
            "uid-1", now=now, limit=2, firestore_client=client, report_page=True
        )
        for _ in range(3)
    ]

    assert pages == [
        frame_requests.FrameCleanupPage(processed=2, cleaned=2),
        frame_requests.FrameCleanupPage(processed=2, cleaned=2),
        frame_requests.FrameCleanupPage(processed=1, cleaned=1),
    ]
    assert collection.rows["gcs-failure"].exists is True
    assert collection.rows["attached"].exists is True
    assert collection.rows["future"].exists is True
    assert all(not collection.rows[f"expired-{index}"].exists for index in range(5))
