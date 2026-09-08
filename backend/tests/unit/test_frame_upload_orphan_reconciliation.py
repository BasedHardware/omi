from datetime import datetime, timezone

from database import frame_requests
from models.frame_request import FrameRequest, FrameRequestState


class _Snapshot:
    def __init__(self, data=None):
        self.exists = data is not None
        self._data = data
        self.id = "frame-1"
        self.reference = _UpdateReference() if data is not None else None

    def to_dict(self):
        return self._data


class _Reference:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or _Snapshot()

    def get(self, transaction=None):
        return self.snapshot


class _UpdateReference:
    def __init__(self):
        self.updates = []

    def update(self, data):
        self.updates.append(data)


class _Collection:
    def __init__(self, reference):
        self.reference = reference

    def document(self, _document_id):
        return self.reference


class _Transaction:
    def __init__(self):
        self.sets = []
        self.updates = []

    def set(self, reference, data, merge=False):
        self.sets.append((reference, data, merge))

    def update(self, reference, data):
        self.updates.append((reference, data))


class _Client:
    def __init__(self, transaction):
        self._transaction = transaction

    def transaction(self):
        return self._transaction


def _request(state: FrameRequestState, *, storage_id: str | None) -> FrameRequest:
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return FrameRequest(
        request_id="frame-1",
        uid="user-1",
        device_id="desktop-1",
        account_generation=3,
        dedupe_key="opaque",
        conversation_id="conversation-1",
        screenshot_id="42",
        state=state,
        created_at=now,
        expires_at=now,
        storage_id=storage_id,
        byte_count=10 if storage_id else 0,
        content_type="image/jpeg" if storage_id else None,
    )


def _install_fakes(monkeypatch, request, *, orphan=None):
    transaction = _Transaction()
    request_ref = _Reference(_Snapshot(request.model_dump(mode="python", exclude_none=True) if request else None))
    orphan_ref = _Reference(_Snapshot(orphan))
    monkeypatch.setattr(frame_requests.firestore, "transactional", lambda function: function)
    monkeypatch.setattr(
        frame_requests,
        "_collection",
        lambda *_args, **_kwargs: _Collection(request_ref),
    )
    monkeypatch.setattr(
        frame_requests,
        "_orphan_collection",
        lambda *_args, **_kwargs: _Collection(orphan_ref),
    )
    return _Client(transaction), transaction, orphan_ref


def _reconcile(client):
    return frame_requests.reconcile_ambiguous_frame_upload(
        "user-1",
        "frame-1",
        device_id="desktop-1",
        account_generation=3,
        storage_id="new-storage",
        byte_count=20,
        content_type="image/jpeg",
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        firestore_client=client,
    )


def test_ambiguous_upload_never_overwrites_an_existing_object_reference(monkeypatch):
    existing = _request(FrameRequestState.uploaded, storage_id="existing-storage")
    client, transaction, orphan_ref = _install_fakes(monkeypatch, existing)

    result = _reconcile(client)

    assert result is not None and result.storage_id == "existing-storage"
    assert transaction.updates == []
    assert len(transaction.sets) == 1
    assert transaction.sets[0][0] is orphan_ref
    assert transaction.sets[0][1]["storage_id"] == "new-storage"
    assert transaction.sets[0][2] is False


def test_ambiguous_upload_records_new_object_independently_before_terminalizing_active_row(monkeypatch):
    active = _request(FrameRequestState.claimed, storage_id=None)
    client, transaction, _ = _install_fakes(monkeypatch, active)

    result = _reconcile(client)

    assert result is not None and result.state == FrameRequestState.failed
    assert result.storage_id is None
    assert transaction.sets[0][1]["storage_id"] == "new-storage"
    assert transaction.updates[0][1]["state"] == FrameRequestState.failed.value
    assert "storage_id" not in transaction.updates[0][1]


def test_missing_request_still_leaves_a_durable_owner_scoped_orphan_receipt(monkeypatch):
    client, transaction, _ = _install_fakes(monkeypatch, None)

    assert _reconcile(client) is None
    assert transaction.sets[0][1]["storage_id"] == "new-storage"
    assert transaction.updates == []


def test_repeated_ambiguity_does_not_reopen_terminal_orphan_receipt(monkeypatch):
    existing = _request(FrameRequestState.uploaded, storage_id="existing-storage")
    client, transaction, _ = _install_fakes(
        monkeypatch,
        existing,
        orphan={
            "storage_id": "new-storage",
            "cleanup_state": "deleted",
            "cleanup_attempts": 1,
        },
    )

    result = _reconcile(client)

    assert result is not None and result.storage_id == "existing-storage"
    assert transaction.sets == []


def test_orphan_cleanup_deletes_object_then_terminalizes_independent_receipt(monkeypatch):
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    snapshot = _Snapshot(
        {
            "storage_id": "new-storage",
            "cleanup_state": "pending",
            "cleanup_attempts": 0,
            "cleanup_next_attempt_at": now,
        }
    )

    class Query:
        def where(self, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def limit(self, _value):
            return self

        def stream(self):
            return iter([snapshot])

    monkeypatch.setattr(frame_requests, "_orphan_collection", lambda *_args, **_kwargs: Query())
    deleted = []

    cleaned = frame_requests.cleanup_ambiguous_frame_upload_pixels(
        "user-1",
        delete_storage=deleted.append,
        now=now,
        firestore_client=object(),
    )

    assert cleaned == 1
    assert deleted == ["new-storage"]
    assert snapshot.reference.updates == [
        {"cleanup_state": "deleted", "cleanup_attempts": 1, "cleanup_next_attempt_at": None}
    ]
