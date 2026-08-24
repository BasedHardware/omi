"""Firestore adapter for the additive just-in-time frame-request queue.

All documents live under the authenticated user's namespace.  The adapter
stores frame metadata and upload references only; it never accepts or emits
pixel bytes.  The pure policy module owns lifecycle and quota rules.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable

from google.cloud import firestore

from database._client import get_firestore_client
from models.frame_request import TERMINAL_FRAME_REQUEST_STATES, FrameRequest, FrameRequestState
from utils.retrieval.frame_request_policy import (
    FRAME_REQUEST_MAX_BATCH,
    FRAME_REQUEST_MAX_PENDING_PER_DEVICE,
    FRAME_REQUEST_MAX_BYTES_PER_DEVICE,
    FRAME_REQUEST_DEDUPE_WINDOW_SECONDS,
    check_device_quota,
    is_expired,
    request_expiry,
    validate_transition,
)

USERS_COLLECTION = "users"
FRAME_REQUESTS_COLLECTION = "frame_requests"


def _get_client(firestore_client: Any | None) -> Any:
    """Resolve the production client at the call boundary.

    Keeping the injectable client keyword-only makes queue policy tests and the
    Firestore emulator independent from ambient ADC while avoiding construction
    of a customer-data client during module import.
    """

    return firestore_client if firestore_client is not None else get_firestore_client()


def _collection(uid: str, *, firestore_client: Any | None = None) -> Any:
    owner_uid = uid.strip()
    if not owner_uid:
        raise ValueError("uid is required")
    client = _get_client(firestore_client)
    return client.collection(USERS_COLLECTION).document(owner_uid).collection(FRAME_REQUESTS_COLLECTION)


def _request_from_snapshot(snapshot: Any) -> FrameRequest:
    raw = snapshot.to_dict() or {}
    raw["request_id"] = str(raw.get("request_id") or snapshot.id)
    return FrameRequest.model_validate(raw)


def _request_data(request: FrameRequest) -> dict[str, Any]:
    return request.model_dump(mode="python", exclude_none=True)


def get_frame_request(uid: str, request_id: str, *, firestore_client: Any | None = None) -> FrameRequest:
    """Read one owner-scoped queue row without exposing another account."""

    snapshot = _collection(uid, firestore_client=firestore_client).document(request_id).get()
    if not snapshot.exists:
        raise KeyError("frame request not found")
    return _request_from_snapshot(snapshot)


def enqueue_frame_request(
    uid: str,
    *,
    device_id: str,
    dedupe_key: str,
    conversation_id: str | None = None,
    screenshot_id: str | None = None,
    account_generation: int = 0,
    requested_ttl_seconds: int | None = None,
    device_retention_seconds: int | None = None,
    now: datetime | None = None,
    firestore_client: Any | None = None,
) -> tuple[FrameRequest, bool]:
    """Create one idempotent request; return ``(request, deduplicated)``.

    The dedupe key is the document id, so retries need one transactional read
    and cannot enqueue duplicate work even when two requests race.
    """

    owner_uid = uid.strip()
    owner_device = device_id.strip()
    stable_dedupe_key = dedupe_key.strip()
    if not owner_uid or not owner_device or not stable_dedupe_key:
        raise ValueError("uid, device_id, and dedupe_key are required")
    if account_generation < 0:
        raise ValueError("account_generation must be nonnegative")
    created = _utc(now or datetime.now(timezone.utc))
    dedupe_window = int(created.timestamp()) // FRAME_REQUEST_DEDUPE_WINDOW_SECONDS
    # Never persist caller wording.  Include the target identities in the
    # opaque key so a reused intent cannot collapse different screenshots or
    # conversations into one attempt.
    dedupe_identity = hashlib.sha256(
        "\x00".join((stable_dedupe_key, conversation_id or "", screenshot_id or "")).encode("utf-8")
    ).hexdigest()
    expires = request_expiry(
        created_at=created,
        requested_ttl_seconds=requested_ttl_seconds,
        device_retention_seconds=device_retention_seconds,
    )
    client = _get_client(firestore_client)
    collection = _collection(owner_uid, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def _create(transaction: Any) -> tuple[dict[str, Any], bool]:
        # Dedupe is scoped to the account generation and a short request
        # window. Terminal/expired attempts are intentionally ignored so a
        # stale row cannot starve a later trigger.
        attempts = [
            _request_from_snapshot(item)
            for item in collection.where(filter=firestore.FieldFilter("device_id", "==", owner_device))
            .where(filter=firestore.FieldFilter("account_generation", "==", account_generation))
            .where(filter=firestore.FieldFilter("dedupe_key", "==", dedupe_identity))
            .where(filter=firestore.FieldFilter("dedupe_window", "==", dedupe_window))
            .order_by("attempt_number", direction=firestore.Query.DESCENDING)
            .limit(FRAME_REQUEST_MAX_BATCH)
            .stream(transaction=transaction)
        ]
        for existing in attempts:
            if existing.state not in {
                FrameRequestState.requested,
                FrameRequestState.claimed,
                FrameRequestState.uploaded,
            }:
                continue
            if not is_expired(existing, now=created):
                return _request_data(existing), True
        attempt_number = max((item.attempt_number for item in attempts), default=-1) + 1
        dedupe_digest = hashlib.sha256(
            f"{dedupe_identity}:{account_generation}:{dedupe_window}:{attempt_number}".encode("utf-8")
        ).hexdigest()
        request_id = f"frame-{dedupe_digest}"
        request = FrameRequest(
            request_id=request_id,
            uid=owner_uid,
            device_id=owner_device,
            account_generation=account_generation,
            dedupe_key=dedupe_identity,
            dedupe_window=dedupe_window,
            attempt_number=attempt_number,
            conversation_id=conversation_id,
            screenshot_id=screenshot_id,
            state=FrameRequestState.requested,
            created_at=created,
            expires_at=expires,
        )
        existing_rows = [
            _request_from_snapshot(item)
            for item in collection.where(filter=firestore.FieldFilter("device_id", "==", owner_device))
            .where(filter=firestore.FieldFilter("account_generation", "==", account_generation))
            .where(
                filter=firestore.FieldFilter(
                    "state",
                    "in",
                    [
                        FrameRequestState.requested.value,
                        FrameRequestState.claimed.value,
                        FrameRequestState.uploaded.value,
                    ],
                )
            )
            .limit(FRAME_REQUEST_MAX_BATCH)
            .stream(transaction=transaction)
        ]
        quota = check_device_quota(existing_rows, uid=owner_uid, device_id=owner_device, now=created)
        if not quota.allowed:
            raise ValueError(f"frame request quota exceeded: {quota.reason}")
        transaction.create(collection.document(request_id), _request_data(request))
        return _request_data(request), False

    data, deduplicated = _create(transaction)
    return FrameRequest.model_validate(data), deduplicated


def list_pending_frame_requests(
    uid: str,
    *,
    device_id: str,
    account_generation: int,
    now: datetime | None = None,
    limit: int = FRAME_REQUEST_MAX_BATCH,
    firestore_client: Any | None = None,
    cleanup_storage: Callable[[str], None] | None = None,
) -> list[FrameRequest]:
    """Return only current-owner requests routed to this exact device."""

    if not 1 <= limit <= FRAME_REQUEST_MAX_BATCH:
        raise ValueError("limit is outside the bounded frame-request window")
    current = _utc(now or datetime.now(timezone.utc))
    # Keep stale rows from occupying the bounded delivery window.  This is a
    # caller-side bounded worker; a scheduled worker can call the same helper.
    prune_expired_frame_requests(
        uid,
        account_generation=account_generation,
        now=current,
        limit=FRAME_REQUEST_MAX_BATCH,
        firestore_client=firestore_client,
        cleanup_storage=cleanup_storage,
    )
    rows: list[FrameRequest] = []
    query = (
        _collection(uid, firestore_client=firestore_client)
        .where(filter=firestore.FieldFilter("device_id", "==", device_id))
        .where(filter=firestore.FieldFilter("account_generation", "==", account_generation))
        .where(filter=firestore.FieldFilter("state", "==", FrameRequestState.requested.value))
        .order_by("created_at", direction=firestore.Query.ASCENDING)
        .limit(limit)
    )
    for snapshot in query.stream():
        request = _request_from_snapshot(snapshot)
        if is_expired(request, now=current):
            continue
        rows.append(request)
    return rows


def transition_frame_request(
    uid: str,
    request_id: str,
    *,
    next_state: FrameRequestState,
    device_id: str,
    account_generation: int,
    terminal_reason: str | None = None,
    storage_id: str | None = None,
    byte_count: int = 0,
    content_type: str | None = None,
    now: datetime | None = None,
    firestore_client: Any | None = None,
    cleanup_storage: Callable[[str], None] | None = None,
) -> FrameRequest:
    """Apply one owner-fenced lifecycle transition transactionally."""

    current_time = _utc(now or datetime.now(timezone.utc))
    client = _get_client(firestore_client)
    ref = _collection(uid, firestore_client=client).document(request_id)
    transaction = client.transaction()

    @firestore.transactional
    def _transition(transaction: Any) -> dict[str, Any]:
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            raise KeyError("frame request not found")
        request = _request_from_snapshot(snapshot)
        validate_transition(
            request,
            next_state=next_state,
            uid=uid,
            device_id=device_id,
            account_generation=account_generation,
            now=current_time,
        )
        if byte_count < 0 or byte_count > 10 * 1024 * 1024:
            raise ValueError("frame upload exceeds the bounded byte limit")
        if next_state != FrameRequestState.uploaded and byte_count:
            raise ValueError("byte_count is only valid when uploading a frame")
        if next_state != FrameRequestState.uploaded and (storage_id or content_type):
            raise ValueError("storage metadata is only valid when uploading a frame")
        if next_state == FrameRequestState.uploaded and not storage_id:
            raise ValueError("uploaded frame requests require storage_id")
        if next_state in TERMINAL_FRAME_REQUEST_STATES - {FrameRequestState.attached} and not terminal_reason:
            raise ValueError("terminal frame requests require a bounded reason")
        if next_state not in TERMINAL_FRAME_REQUEST_STATES and terminal_reason:
            raise ValueError("active frame requests must not carry a terminal reason")
        if next_state == FrameRequestState.attached and not request.conversation_id:
            raise ValueError("only conversation-bound requests may be attached")
        if next_state == FrameRequestState.attached and (storage_id or byte_count or content_type):
            raise ValueError("attached transition cannot replace upload metadata")
        if (
            next_state in TERMINAL_FRAME_REQUEST_STATES - {FrameRequestState.attached}
            and cleanup_storage
            and request.storage_id
        ):
            # Pixels are temporary until the attached transition. Delete them
            # before recording a terminal outcome; a storage failure leaves the
            # row retryable rather than orphaning data.
            cleanup_storage(request.storage_id)
        if next_state == FrameRequestState.uploaded:
            # Byte quota is enforced at the upload transition, after the
            # object has been authenticated and before metadata is committed.
            active_rows = [
                _request_from_snapshot(item)
                for item in _collection(uid, firestore_client=client)
                .where(filter=firestore.FieldFilter("device_id", "==", device_id))
                .where(filter=firestore.FieldFilter("account_generation", "==", account_generation))
                .where(
                    filter=firestore.FieldFilter(
                        "state",
                        "in",
                        [
                            FrameRequestState.requested.value,
                            FrameRequestState.claimed.value,
                            FrameRequestState.uploaded.value,
                        ],
                    )
                )
                .limit(FRAME_REQUEST_MAX_PENDING_PER_DEVICE + 1)
                .stream(transaction=transaction)
            ]
            quota = check_device_quota(
                active_rows,
                uid=uid,
                device_id=device_id,
                now=current_time,
                additional_bytes=byte_count,
            )
            if quota.pending_bytes + byte_count > FRAME_REQUEST_MAX_BYTES_PER_DEVICE:
                raise ValueError("frame request quota exceeded: pending_bytes")
        update: dict[str, Any] = {
            "state": next_state.value,
            "terminal_reason": terminal_reason,
        }
        if next_state == FrameRequestState.claimed:
            update["claimed_at"] = current_time
        if next_state == FrameRequestState.uploaded:
            update.update(
                {
                    "uploaded_at": current_time,
                    "storage_id": storage_id,
                    "byte_count": byte_count,
                    "content_type": content_type,
                }
            )
        if next_state == FrameRequestState.attached:
            update["attached_at"] = current_time
            # Attached conversation evidence follows conversation lifetime; do
            # not leave a temporary TTL for a cleanup worker to delete.
            update["expires_at"] = request.created_at
        candidate = FrameRequest.model_validate({**_request_data(request), **update})
        transaction.update(ref, _request_data(candidate))
        return _request_data(candidate)

    return FrameRequest.model_validate(_transition(transaction))


def prune_expired_frame_requests(
    uid: str,
    *,
    account_generation: int | None = None,
    now: datetime | None = None,
    limit: int = FRAME_REQUEST_MAX_BATCH,
    firestore_client: Any | None = None,
    cleanup_storage: Callable[[str], None] | None = None,
) -> int:
    """Mark stale unbound requests pruned and optionally delete their pixels."""

    if not 1 <= limit <= FRAME_REQUEST_MAX_BATCH:
        raise ValueError("limit is outside the bounded frame-request window")
    current = _utc(now or datetime.now(timezone.utc))
    client = _get_client(firestore_client)
    query = (
        _collection(uid, firestore_client=client)
        .where(filter=firestore.FieldFilter("state", "in", ["requested", "claimed", "uploaded"]))
        .order_by("expires_at", direction=firestore.Query.ASCENDING)
    )
    if account_generation is not None:
        query = query.where(filter=firestore.FieldFilter("account_generation", "==", account_generation))
    changed = 0
    for snapshot in list(query.limit(limit).stream()):
        row_transaction = client.transaction()

        @firestore.transactional
        def _prune_one(transaction: Any) -> tuple[bool, str | None]:
            fresh = snapshot.reference.get(transaction=transaction)
            if not fresh.exists:
                return False, None
            request = _request_from_snapshot(fresh)
            # Re-read inside a transaction so a concurrent upload/promotion
            # cannot be overwritten by this expiry worker.
            if request.state == FrameRequestState.attached or not is_expired(request, now=current):
                return False, None
            candidate = FrameRequest.model_validate(
                {
                    **_request_data(request),
                    "state": FrameRequestState.pruned.value,
                    "terminal_reason": "retention_expired",
                }
            )
            transaction.update(snapshot.reference, _request_data(candidate))
            return True, request.storage_id

        pruned, storage_id = _prune_one(row_transaction)
        if storage_id and cleanup_storage:
            # Metadata is terminal before the external object delete. Cleanup
            # is idempotent and a retrying worker can remove a transiently
            # unavailable object without reopening the lifecycle row.
            cleanup_storage(storage_id)
        if pruned:
            changed += 1
    return changed


def delete_frame_requests_for_conversation(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any | None = None,
    batch_size: int = 450,
) -> int:
    """Delete queue metadata and attached-frame references with its conversation.

    Conversation images are permanent for the conversation lifetime, but that
    lifetime ends on an owner-authorized conversation deletion. This helper is
    bounded and never deletes another conversation's rows.
    """

    if not conversation_id.strip():
        raise ValueError("conversation_id is required")
    client = _get_client(firestore_client)
    rows = list(
        _collection(uid, firestore_client=client)
        .where(filter=firestore.FieldFilter("conversation_id", "==", conversation_id))
        .stream()
    )
    deleted = 0
    for start in range(0, len(rows), batch_size):
        batch = client.batch()
        for snapshot in rows[start : start + batch_size]:
            batch.delete(snapshot.reference)
            deleted += 1
        batch.commit()
    return deleted


def list_frame_request_storage_ids(
    uid: str,
    *,
    conversation_id: str | None = None,
    firestore_client: Any | None = None,
    limit: int = 5000,
) -> list[str]:
    """Return only opaque object references for an owner-scoped cleanup."""

    if not 1 <= limit <= 10000:
        raise ValueError("limit is outside the bounded cleanup window")
    query = _collection(uid, firestore_client=firestore_client)
    if conversation_id is not None:
        if not conversation_id.strip():
            raise ValueError("conversation_id is required")
        query = query.where(filter=firestore.FieldFilter("conversation_id", "==", conversation_id))
    result: list[str] = []
    for snapshot in query.limit(limit).stream():
        value = (snapshot.to_dict() or {}).get("storage_id")
        if isinstance(value, str) and value.strip() and "/" not in value and "\\" not in value:
            result.append(value.strip())
    return result


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
