"""Firestore adapter for the additive just-in-time frame-request queue.

All documents live under the authenticated user's namespace.  The adapter
stores frame metadata and upload references only; it never accepts or emits
pixel bytes.  The pure policy module owns lifecycle and quota rules.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from google.cloud import firestore

from database._client import get_data_plane_firestore_client
from database.conversations import conversations_collection, prepare_photo_for_write
from database.durable_queue import ProcessOutcome, drain_isolated
from database.firestore_index_registry import (
    FRAME_REQUEST_METADATA_EXPIRY_QUERY,
    FRAME_VISION_OUTPUT_EXPIRY_QUERY,
)
from database.read_boundary import parse_payload_strict, parse_snapshot_strict
from models.frame_request import (
    TERMINAL_FRAME_REQUEST_STATES,
    FrameRequest,
    FrameRequestCleanupState,
    FrameRequestState,
)
from utils.retrieval.frame_request_policy import (
    FRAME_REQUEST_MAX_BATCH,
    FRAME_REQUEST_MAX_BYTES_PER_DEVICE,
    FRAME_REQUEST_MAX_BYTES_PER_CONVERSATION,
    FRAME_REQUEST_MAX_TTL_SECONDS,
    FRAME_REQUEST_DEDUPE_WINDOW_SECONDS,
    FRAME_REQUEST_MAX_ATTACHED_PER_CONVERSATION,
    check_device_quota,
    is_expired,
    request_expiry,
    validate_transition,
)

USERS_COLLECTION = "users"
FRAME_REQUESTS_COLLECTION = "frame_requests"
FRAME_UPLOAD_ORPHANS_COLLECTION = "frame_upload_orphans"
FRAME_DELETION_OUTBOX_COLLECTION = "frame_deletion_outbox"
FRAME_VISION_RECEIPTS_COLLECTION = "frame_vision_receipts"


@dataclass(frozen=True)
class FrameCleanupPage:
    processed: int
    cleaned: int


def _get_client(firestore_client: Any | None) -> Any:
    """Resolve the production client at the call boundary.

    Keeping the injectable client keyword-only makes queue policy tests and the
    Firestore emulator independent from ambient ADC while avoiding construction
    of a customer-data client during module import.
    """

    return firestore_client if firestore_client is not None else get_data_plane_firestore_client()


def _collection(uid: str, *, firestore_client: Any | None = None) -> Any:
    owner_uid = uid.strip()
    if not owner_uid:
        raise ValueError("uid is required")
    client = _get_client(firestore_client)
    return client.collection(USERS_COLLECTION).document(owner_uid).collection(FRAME_REQUESTS_COLLECTION)


def _orphan_collection(uid: str, *, firestore_client: Any | None = None) -> Any:
    owner_uid = uid.strip()
    if not owner_uid:
        raise ValueError("uid is required")
    client = _get_client(firestore_client)
    return client.collection(USERS_COLLECTION).document(owner_uid).collection(FRAME_UPLOAD_ORPHANS_COLLECTION)


def _deletion_outbox_collection(uid: str, *, firestore_client: Any | None = None) -> Any:
    owner_uid = uid.strip()
    if not owner_uid:
        raise ValueError("uid is required")
    client = _get_client(firestore_client)
    return client.collection(USERS_COLLECTION).document(owner_uid).collection(FRAME_DELETION_OUTBOX_COLLECTION)


def _deletion_receipt_id(conversation_id: str, storage_id: str) -> str:
    return hashlib.sha256(f"{conversation_id}\0{storage_id}".encode("utf-8")).hexdigest()


def reserve_frame_vision_invocation(
    uid: str,
    authority_key: str,
    *,
    request_id: str,
    account_generation: int,
    now: datetime | None = None,
    firestore_client: Any | None = None,
) -> dict[str, Any]:
    """Durably reserve the sole paid invocation for one stable chat turn.

    The receipt is written *before* provider egress. An expired lease is an
    honest indeterminate outcome, not permission to pay twice after a crash.
    """
    if not authority_key.strip():
        raise ValueError("stable vision authority is required")
    current = _utc(now or datetime.now(timezone.utc))
    client = _get_client(firestore_client)
    receipt_id = hashlib.sha256(authority_key.encode("utf-8")).hexdigest()
    ref = (
        client.collection(USERS_COLLECTION)
        .document(uid)
        .collection(FRAME_VISION_RECEIPTS_COLLECTION)
        .document(receipt_id)
    )
    transaction = client.transaction()

    @firestore.transactional
    def _reserve(transaction: Any) -> dict[str, Any]:
        snapshot = ref.get(transaction=transaction)
        if snapshot.exists:
            row = snapshot.to_dict() or {}
            if row.get("request_id") != request_id or row.get("account_generation") != account_generation:
                raise PermissionError("vision receipt authority mismatch")
            return row
        row = {
            "request_id": request_id,
            "account_generation": account_generation,
            "state": "invoked",
            "created_at": current,
            "lease_expires_at": current + timedelta(minutes=5),
        }
        transaction.create(ref, row)
        return {**row, "reserved": True}

    return _reserve(transaction)


def complete_frame_vision_invocation(
    uid: str,
    authority_key: str,
    *,
    request_id: str,
    account_generation: int,
    description: str,
    now: datetime | None = None,
    firestore_client: Any | None = None,
) -> None:
    """Store only the bounded derived result; never pixels or prompt content."""
    bounded = description[:4000]
    ref = (
        _get_client(firestore_client)
        .collection(USERS_COLLECTION)
        .document(uid)
        .collection(FRAME_VISION_RECEIPTS_COLLECTION)
        .document(hashlib.sha256(authority_key.encode("utf-8")).hexdigest())
    )
    snapshot = ref.get()
    row = snapshot.to_dict() if snapshot.exists else {}
    if row.get("request_id") != request_id or row.get("account_generation") != account_generation:
        raise PermissionError("vision receipt authority mismatch")
    completed_at = _utc(now or datetime.now(timezone.utc))
    ref.update(
        {
            "state": "completed",
            "description": bounded,
            "completed_at": completed_at,
            "output_expires_at": completed_at + timedelta(seconds=FRAME_REQUEST_MAX_TTL_SECONDS),
        }
    )


def persist_conversation_frame_deletion_outbox(
    uid: str,
    conversation_id: str,
    storage_ids: list[str],
    *,
    now: datetime | None = None,
    firestore_client: Any | None = None,
) -> None:
    """Durably record every object before its owning conversation is removed."""

    if not conversation_id.strip():
        raise ValueError("conversation_id is required")
    current = _utc(now or datetime.now(timezone.utc))
    client = _get_client(firestore_client)
    collection = _deletion_outbox_collection(uid, firestore_client=client)
    for storage_id in dict.fromkeys(storage_ids):
        if not storage_id or "/" in storage_id or "\\" in storage_id:
            raise ValueError("invalid frame storage id")
        collection.document(_deletion_receipt_id(conversation_id, storage_id)).set(
            {
                "conversation_id": conversation_id,
                "storage_id": storage_id,
                "cleanup_next_attempt_at": current,
                "cleanup_attempts": 0,
            },
            merge=True,
        )


def acknowledge_conversation_frame_deletion(
    uid: str,
    conversation_id: str,
    storage_id: str,
    *,
    firestore_client: Any | None = None,
) -> None:
    _deletion_outbox_collection(uid, firestore_client=firestore_client).document(
        _deletion_receipt_id(conversation_id, storage_id)
    ).delete()


def cleanup_conversation_frame_deletion_outbox(
    uid: str,
    *,
    delete_storage: Callable[[str], None],
    now: datetime | None = None,
    limit: int = FRAME_REQUEST_MAX_BATCH,
    firestore_client: Any | None = None,
    report_page: bool = False,
) -> int | FrameCleanupPage:
    """Retry conversation-owned object deletion after the conversation is gone."""

    current = _utc(now or datetime.now(timezone.utc))
    query = (
        _deletion_outbox_collection(uid, firestore_client=firestore_client)
        .where(filter=firestore.FieldFilter("cleanup_next_attempt_at", "<=", current))
        .order_by("cleanup_next_attempt_at", direction=firestore.Query.ASCENDING)
        .limit(limit)
    )
    snapshots = list(query.stream())
    processed = cleaned = 0

    def process_one(snapshot: Any) -> ProcessOutcome:
        nonlocal processed, cleaned
        row = snapshot.to_dict() or {}
        storage_id = row.get("storage_id")
        attempts = max(0, int(row.get("cleanup_attempts") or 0))
        processed += 1
        if not isinstance(storage_id, str) or not storage_id or "/" in storage_id or "\\" in storage_id:
            snapshot.reference.delete()
            return ProcessOutcome.reject("invalid frame storage id", reason="malformed")
        try:
            delete_storage(storage_id)
        except Exception as exc:
            snapshot.reference.update(
                {
                    "cleanup_attempts": attempts + 1,
                    "cleanup_next_attempt_at": current + timedelta(seconds=min(86400, 2 ** min(attempts, 16))),
                    "last_error_text": str(exc)[:2000],
                }
            )
            return ProcessOutcome.retry(str(exc), reason="storage_delete_failed")
        snapshot.reference.delete()
        cleaned += 1
        return ProcessOutcome.ack()

    drain_isolated(snapshots, process_one)
    page = FrameCleanupPage(processed=processed, cleaned=cleaned)
    return page if report_page else page.cleaned


def _request_from_snapshot(snapshot: Any) -> FrameRequest:
    return parse_snapshot_strict(FrameRequest, snapshot, document_id_field="request_id")


def _request_from_payload(payload: dict[str, Any], *, document_path: str) -> FrameRequest:
    return parse_payload_strict(FrameRequest, payload, document_path=document_path)


def _request_path(uid: str, request_id: str) -> str:
    return f"{USERS_COLLECTION}/{uid}/{FRAME_REQUESTS_COLLECTION}/{request_id}"


def _request_data(request: FrameRequest) -> dict[str, Any]:
    return request.model_dump(mode="python", exclude_none=True)


def get_frame_request(uid: str, request_id: str, *, firestore_client: Any | None = None) -> FrameRequest:
    """Read one owner-scoped queue row without exposing another account."""

    snapshot = _collection(uid, firestore_client=firestore_client).document(request_id).get()
    if not snapshot.exists:
        raise KeyError("frame request not found")
    return _request_from_snapshot(snapshot)


def list_attached_frame_requests(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any | None = None,
    limit: int = 2,
) -> list[FrameRequest]:
    """Return the bounded set used to enforce one permanent keyframe."""

    if not conversation_id.strip() or not 1 <= limit <= 2:
        raise ValueError("invalid conversation frame-request lookup")
    query = (
        _collection(uid, firestore_client=firestore_client)
        .where(filter=firestore.FieldFilter("conversation_id", "==", conversation_id))
        .where(filter=firestore.FieldFilter("state", "==", FrameRequestState.attached.value))
        .limit(limit)
    )
    return [_request_from_snapshot(snapshot) for snapshot in query.stream()]


def attach_frame_request_to_conversation(
    uid: str,
    request_id: str,
    *,
    device_id: str,
    account_generation: int,
    conversation_id: str,
    permanent_storage_id: str,
    now: datetime | None = None,
    firestore_client: Any | None = None,
) -> FrameRequest:
    """Atomically attach one uploaded frame and its permanent photo metadata.

    The row, photo subcollection document, conversation marker, and one-photo
    invariant are committed in a single transaction. A retry after a committed
    response/transport ambiguity returns the already-attached row without
    touching the permanent object.
    """

    if not conversation_id.strip() or not permanent_storage_id.strip():
        raise ValueError("conversation_id and permanent_storage_id are required")
    current_time = _utc(now or datetime.now(timezone.utc))
    client = _get_client(firestore_client)
    ref = _collection(uid, firestore_client=client).document(request_id)
    conversation_ref = (
        client.collection(USERS_COLLECTION)
        .document(uid.strip())
        .collection(conversations_collection)
        .document(conversation_id)
    )
    photos_ref = conversation_ref.collection("photos")
    photo_ref = photos_ref.document(request_id)
    promotion_receipt_ref = _orphan_collection(uid, firestore_client=client).document(
        hashlib.sha256(permanent_storage_id.encode("utf-8")).hexdigest()
    )
    transaction = client.transaction()

    @firestore.transactional
    def _attach(transaction: Any) -> dict[str, Any]:
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            raise KeyError("frame request not found")
        request = _request_from_snapshot(snapshot)
        if request.uid != uid or request.device_id != device_id or request.account_generation != account_generation:
            raise PermissionError("frame request owner or account generation mismatch")
        if request.conversation_id != conversation_id:
            raise PermissionError("conversation ownership mismatch")
        if request.state == FrameRequestState.attached:
            if request.storage_id != permanent_storage_id:
                raise ValueError("attached frame uses a different permanent object")
            # A concurrent caller may have reserved the same deterministic copy
            # receipt after the winner committed. Clear it transactionally so
            # cleanup can never delete referenced permanent evidence.
            transaction.delete(promotion_receipt_ref)
            return _request_data(request)
        if request.state != FrameRequestState.uploaded or not request.storage_id:
            raise ValueError("only uploaded frame requests may be promoted")

        conversation_snapshot = conversation_ref.get(transaction=transaction)
        if not conversation_snapshot.exists:
            raise KeyError("conversation not found")

        # Firestore reads in this transaction establish a contention fence for
        # all attached rows in the conversation; a concurrent winner retries
        # this transaction and is then observed as the existing row above.
        attached_rows = [
            _request_from_snapshot(item)
            for item in _collection(uid, firestore_client=client)
            .where(filter=firestore.FieldFilter("conversation_id", "==", conversation_id))
            .where(filter=firestore.FieldFilter("state", "==", FrameRequestState.attached.value))
            .limit(FRAME_REQUEST_MAX_ATTACHED_PER_CONVERSATION + 1)
            .stream(transaction=transaction)
        ]
        if any(item.request_id != request_id for item in attached_rows):
            raise ValueError("conversation already has permanent frame evidence")
        if (
            sum(item.byte_count for item in attached_rows) + request.byte_count
            > FRAME_REQUEST_MAX_BYTES_PER_CONVERSATION
        ):
            raise ValueError("conversation frame evidence byte budget exceeded")

        existing_photo = photo_ref.get(transaction=transaction)
        if existing_photo.exists:
            existing_storage_id = (existing_photo.to_dict() or {}).get("storage_id")
            if existing_storage_id != permanent_storage_id:
                raise ValueError("conversation photo id is already used")
        else:
            level = (conversation_snapshot.to_dict() or {}).get("data_protection_level", "standard")
            photo_data = prepare_photo_for_write(
                {
                    "id": request.request_id,
                    "base64": "",
                    "storage_id": permanent_storage_id,
                    "content_type": request.content_type,
                    "description": "Just-in-time frame evidence",
                    "discarded": False,
                    "created_at": request.created_at,
                },
                uid,
                level,
            )
            transaction.set(photo_ref, photo_data)
        transaction.update(conversation_ref, {"has_content": True, "has_photos": True})
        candidate = _request_from_payload(
            {
                **_request_data(request),
                "state": FrameRequestState.attached.value,
                "attached_at": current_time,
                "expires_at": request.created_at,
                "cleanup_state": FrameRequestCleanupState.permanent.value,
                "cleanup_next_attempt_at": None,
                "storage_id": permanent_storage_id,
            },
            document_path=_request_path(uid, request_id),
        )
        transaction.update(ref, _request_data(candidate))
        transaction.delete(promotion_receipt_ref)
        return _request_data(candidate)

    return _request_from_payload(_attach(transaction), document_path=_request_path(uid, request_id))


def reserve_frame_promotion_copy(
    uid: str,
    request_id: str,
    permanent_storage_id: str,
    *,
    now: datetime | None = None,
    firestore_client: Any | None = None,
) -> None:
    """Persist a cleanup receipt before copying into the no-expiry bucket.

    Successful attachment deletes the receipt in the same transaction as the
    permanent reference. A failed/ambiguous promotion therefore leaves either
    a referenced permanent object or a discoverable object due for cleanup.
    """

    current = _utc(now or datetime.now(timezone.utc))
    if not request_id.strip() or not permanent_storage_id.strip():
        raise ValueError("promotion receipt identities are required")
    receipt = _orphan_collection(uid, firestore_client=firestore_client).document(
        hashlib.sha256(permanent_storage_id.encode("utf-8")).hexdigest()
    )
    receipt.set(
        {
            "storage_id": permanent_storage_id,
            "request_id": request_id,
            "cleanup_state": FrameRequestCleanupState.pending.value,
            "cleanup_attempts": 0,
            # Leave ample time for copy + Firestore transaction retries while
            # remaining far inside the temporary retention deadline.
            "cleanup_next_attempt_at": current + timedelta(hours=1),
            "created_at": current,
            "kind": "promotion_copy",
        },
        merge=False,
    )


def reserve_frame_storage_cleanup(
    uid: str,
    request_id: str,
    storage_id: str,
    *,
    now: datetime | None = None,
    firestore_client: Any | None = None,
) -> None:
    """Persist an independently retryable cleanup receipt for a displaced object."""

    current = _utc(now or datetime.now(timezone.utc))
    receipt = _orphan_collection(uid, firestore_client=firestore_client).document(
        hashlib.sha256(storage_id.encode("utf-8")).hexdigest()
    )
    receipt.set(
        {
            "storage_id": storage_id,
            "request_id": request_id,
            "cleanup_state": FrameRequestCleanupState.pending.value,
            "cleanup_attempts": 0,
            "cleanup_next_attempt_at": current + timedelta(hours=1),
            "created_at": current,
            "kind": "displaced_temporary",
        },
        merge=False,
    )


def acknowledge_frame_storage_cleanup(
    uid: str,
    storage_id: str,
    *,
    firestore_client: Any | None = None,
) -> None:
    _orphan_collection(uid, firestore_client=firestore_client).document(
        hashlib.sha256(storage_id.encode("utf-8")).hexdigest()
    ).delete()


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
        # Dedupe is scoped to the account generation and the full active
        # logical-request lifetime. ``dedupe_window`` remains an observability
        # bucket/index hint, never an expiry boundary for active work.
        attempts = [
            _request_from_snapshot(item)
            for item in collection.where(filter=firestore.FieldFilter("device_id", "==", owner_device))
            .where(filter=firestore.FieldFilter("account_generation", "==", account_generation))
            .where(filter=firestore.FieldFilter("dedupe_key", "==", dedupe_identity))
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
        if conversation_id:
            conversation_rows = [
                _request_from_snapshot(item)
                for item in collection.where(filter=firestore.FieldFilter("conversation_id", "==", conversation_id))
                .where(
                    filter=firestore.FieldFilter(
                        "state",
                        "in",
                        [
                            FrameRequestState.requested.value,
                            FrameRequestState.claimed.value,
                            FrameRequestState.uploaded.value,
                            FrameRequestState.attached.value,
                        ],
                    )
                )
                .limit(FRAME_REQUEST_MAX_ATTACHED_PER_CONVERSATION + 1)
                .stream(transaction=transaction)
            ]
            if conversation_rows:
                raise ValueError("conversation already has an active frame request")
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
    return (
        _request_from_payload(
            data,
            document_path=_request_path(owner_uid, str(data["request_id"])),
        ),
        deduplicated,
    )


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
        # External deletion belongs to the scheduled retention worker.  A
        # device polling endpoint must not be the only janitor.
        cleanup_storage=None,
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


def list_recoverable_frame_requests(
    uid: str,
    *,
    device_id: str,
    account_generation: int,
    now: datetime | None = None,
    limit: int = FRAME_REQUEST_MAX_BATCH,
    firestore_client: Any | None = None,
) -> list[FrameRequest]:
    """Return requested/claimed/uploaded rows for in-flight device recovery."""

    if not 1 <= limit <= FRAME_REQUEST_MAX_BATCH:
        raise ValueError("limit is outside the bounded frame-request window")
    current = _utc(now or datetime.now(timezone.utc))
    query = (
        _collection(uid, firestore_client=firestore_client)
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
        .order_by("created_at", direction=firestore.Query.ASCENDING)
        .limit(limit)
    )
    return [
        request
        for snapshot in query.stream()
        if not is_expired(request := _request_from_snapshot(snapshot), now=current)
    ]


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
                # Sum the full bounded active set; using only the pending-count
                # cap would let old uploaded rows evade the byte quota.
                .limit(FRAME_REQUEST_MAX_BATCH).stream(transaction=transaction)
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
            update["cleanup_state"] = FrameRequestCleanupState.permanent.value
        elif request.storage_id and next_state in TERMINAL_FRAME_REQUEST_STATES:
            # Terminal metadata must not imply that the external object was
            # deleted. A scheduled worker retries this independently.
            update["cleanup_state"] = FrameRequestCleanupState.pending.value
            update["cleanup_next_attempt_at"] = current_time
        elif next_state == FrameRequestState.uploaded:
            update["cleanup_state"] = FrameRequestCleanupState.pending.value
            update["cleanup_next_attempt_at"] = current_time
        candidate = _request_from_payload(
            {**_request_data(request), **update},
            document_path=_request_path(uid, request_id),
        )
        transaction.update(ref, _request_data(candidate))
        return _request_data(candidate)

    return _request_from_payload(_transition(transaction), document_path=_request_path(uid, request_id))


def reconcile_ambiguous_frame_upload(
    uid: str,
    request_id: str,
    *,
    device_id: str,
    account_generation: int,
    storage_id: str,
    byte_count: int,
    content_type: str | None,
    now: datetime | None = None,
    firestore_client: Any | None = None,
) -> FrameRequest | None:
    """Resolve an uncertain upload commit without losing an object reference.

    If the upload transition committed, return the uploaded/attached row. If a
    strongly consistent read does not find that exact reference, persist an
    independent owner-scoped orphan receipt for the newly uploaded object. The
    existing request reference is never overwritten, and the object is never
    deleted in this ambiguity path.
    """

    current_time = _utc(now or datetime.now(timezone.utc))
    client = _get_client(firestore_client)
    ref = _collection(uid, firestore_client=client).document(request_id)
    orphan_ref = _orphan_collection(uid, firestore_client=client).document(
        hashlib.sha256(storage_id.encode("utf-8")).hexdigest()
    )
    transaction = client.transaction()

    @firestore.transactional
    def _reconcile(transaction: Any) -> dict[str, Any] | None:
        snapshot = ref.get(transaction=transaction)
        orphan_snapshot = orphan_ref.get(transaction=transaction)
        orphan_data = {
            "storage_id": storage_id,
            "request_id": request_id,
            "cleanup_state": FrameRequestCleanupState.pending.value,
            "cleanup_attempts": 0,
            "cleanup_next_attempt_at": current_time,
            "created_at": current_time,
        }

        def ensure_orphan_receipt() -> None:
            # A repeated ambiguity reconciliation must not reset a receipt
            # that the cleanup worker already terminalized.
            if not orphan_snapshot.exists:
                transaction.set(orphan_ref, orphan_data)

        if not snapshot.exists:
            ensure_orphan_receipt()
            return None
        request = _request_from_snapshot(snapshot)
        if request.uid != uid or request.device_id != device_id or request.account_generation != account_generation:
            ensure_orphan_receipt()
            return None
        if request.storage_id == storage_id:
            return _request_data(request)
        ensure_orphan_receipt()
        if request.state in TERMINAL_FRAME_REQUEST_STATES or request.storage_id:
            return _request_data(request)
        candidate = _request_from_payload(
            {
                **_request_data(request),
                "state": FrameRequestState.failed.value,
                "terminal_reason": "upload_commit_ambiguous",
            },
            document_path=_request_path(uid, request_id),
        )
        transaction.update(ref, _request_data(candidate))
        return _request_data(candidate)

    result = _reconcile(transaction)
    return _request_from_payload(result, document_path=_request_path(uid, request_id)) if result else None


def cleanup_ambiguous_frame_upload_pixels(
    uid: str,
    *,
    delete_storage: Callable[[str], None],
    now: datetime | None = None,
    limit: int = FRAME_REQUEST_MAX_BATCH,
    firestore_client: Any | None = None,
    report_page: bool = False,
) -> int | FrameCleanupPage:
    """Converge durable ambiguous-upload receipts independently of request rows."""

    if not 1 <= limit <= FRAME_REQUEST_MAX_BATCH:
        raise ValueError("limit is outside the bounded frame-request window")
    current = _utc(now or datetime.now(timezone.utc))
    query = (
        _orphan_collection(uid, firestore_client=firestore_client)
        .where(filter=firestore.FieldFilter("cleanup_next_attempt_at", "<=", current))
        .order_by("cleanup_next_attempt_at", direction=firestore.Query.ASCENDING)
        .limit(limit)
    )
    processed = cleaned = 0
    for snapshot in query.stream():
        row = snapshot.to_dict() or {}
        storage_id = row.get("storage_id")
        cleanup_state = row.get("cleanup_state")
        if (
            not isinstance(storage_id, str)
            or not storage_id.strip()
            or "/" in storage_id
            or "\\" in storage_id
            or cleanup_state not in {FrameRequestCleanupState.pending.value, FrameRequestCleanupState.failed.value}
        ):
            snapshot.reference.delete()
            processed += 1
            continue
        processed += 1
        attempts = max(0, int(row.get("cleanup_attempts") or 0))
        try:
            delete_storage(storage_id)
        except Exception:
            retry_at = current + timedelta(seconds=min(24 * 60 * 60, 2 ** min(attempts, 16)))
            snapshot.reference.update(
                {
                    "cleanup_state": FrameRequestCleanupState.failed.value,
                    "cleanup_attempts": attempts + 1,
                    "cleanup_next_attempt_at": retry_at,
                }
            )
            continue
        snapshot.reference.update(
            {
                "cleanup_state": FrameRequestCleanupState.deleted.value,
                "cleanup_attempts": attempts + 1,
                "cleanup_next_attempt_at": None,
            }
        )
        cleaned += 1
    page = FrameCleanupPage(processed=processed, cleaned=cleaned)
    return page if report_page else page.cleaned


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
        def _prune_one(transaction: Any) -> bool:
            fresh = snapshot.reference.get(transaction=transaction)
            if not fresh.exists:
                return False
            request = _request_from_snapshot(fresh)
            # Re-read inside a transaction so a concurrent upload/promotion
            # cannot be overwritten by this expiry worker.
            if request.state == FrameRequestState.attached or not is_expired(request, now=current):
                return False
            candidate = _request_from_payload(
                {
                    **_request_data(request),
                    "state": FrameRequestState.pruned.value,
                    "terminal_reason": "retention_expired",
                    "cleanup_state": (
                        FrameRequestCleanupState.pending.value
                        if request.storage_id
                        else FrameRequestCleanupState.not_required.value
                    ),
                    "cleanup_next_attempt_at": current,
                },
                document_path=_request_path(uid, snapshot.id),
            )
            transaction.update(snapshot.reference, _request_data(candidate))
            return True

        pruned = _prune_one(row_transaction)
        if pruned:
            changed += 1
    return changed


def cleanup_frame_request_pixels(
    uid: str,
    *,
    delete_storage: Callable[[str], None],
    now: datetime | None = None,
    limit: int = FRAME_REQUEST_MAX_BATCH,
    firestore_client: Any | None = None,
    report_page: bool = False,
) -> int | FrameCleanupPage:
    """Retry external deletion independently of queue delivery or lifecycle state.

    A failed GCS delete never reopens or hides the terminal Firestore row. The
    retry state is deliberately content-free and bounded, so a scheduled job
    can converge even when no device calls the pending endpoint.
    """

    if not 1 <= limit <= FRAME_REQUEST_MAX_BATCH:
        raise ValueError("limit is outside the bounded frame-request window")
    current = _utc(now or datetime.now(timezone.utc))
    client = _get_client(firestore_client)
    query = (
        _collection(uid, firestore_client=client)
        .where(
            filter=firestore.FieldFilter(
                "state",
                "in",
                [state.value for state in TERMINAL_FRAME_REQUEST_STATES if state != FrameRequestState.attached],
            )
        )
        .where(filter=firestore.FieldFilter("cleanup_state", "in", ["pending", "failed"]))
        .where(filter=firestore.FieldFilter("cleanup_next_attempt_at", "<=", current))
        .order_by("cleanup_next_attempt_at", direction=firestore.Query.ASCENDING)
        .limit(limit)
    )
    processed = cleaned = 0
    for snapshot in query.stream():
        request = _request_from_snapshot(snapshot)
        if not request.storage_id or request.cleanup_state not in {
            FrameRequestCleanupState.pending,
            FrameRequestCleanupState.failed,
        }:
            continue
        processed += 1
        try:
            delete_storage(request.storage_id)
        except Exception:
            # Do not persist exception text or pixels in telemetry/metadata.
            retry_at = current + timedelta(seconds=min(24 * 60 * 60, 2 ** min(request.cleanup_attempts, 16)))
            ref = snapshot.reference
            ref.update(
                {
                    "cleanup_state": FrameRequestCleanupState.failed.value,
                    "cleanup_attempts": request.cleanup_attempts + 1,
                    "cleanup_next_attempt_at": retry_at,
                }
            )
            continue
        snapshot.reference.update(
            {
                "cleanup_state": FrameRequestCleanupState.deleted.value,
                "cleanup_attempts": request.cleanup_attempts + 1,
                "cleanup_next_attempt_at": None,
            }
        )
        cleaned += 1
    page = FrameCleanupPage(processed=processed, cleaned=cleaned)
    return page if report_page else page.cleaned


def cleanup_expired_frame_vision_outputs(
    uid: str,
    *,
    now: datetime | None = None,
    limit: int = FRAME_REQUEST_MAX_BATCH,
    firestore_client: Any | None = None,
    report_page: bool = False,
) -> int | FrameCleanupPage:
    """Strip expired derived descriptions while preserving at-most-once authority.

    The surviving receipt is deliberately content-free and non-expiring. A
    crash after provider egress must never turn retention cleanup into
    permission to invoke the provider again.
    """

    if not 1 <= limit <= FRAME_REQUEST_MAX_BATCH:
        raise ValueError("limit is outside the bounded frame-request window")
    current = _utc(now or datetime.now(timezone.utc))
    client = _get_client(firestore_client)
    query = FRAME_VISION_OUTPUT_EXPIRY_QUERY.build(
        client.collection(USERS_COLLECTION).document(uid).collection(FRAME_VISION_RECEIPTS_COLLECTION),
        {"now": current},
        field_filter_factory=firestore.FieldFilter,
    ).order_by("output_expires_at", direction=firestore.Query.ASCENDING)
    processed = stripped = 0
    for snapshot in query.limit(limit).stream():
        processed += 1
        transaction = client.transaction()

        @firestore.transactional
        def _strip_one(transaction: Any) -> bool:
            fresh = snapshot.reference.get(transaction=transaction)
            if not fresh.exists:
                return False
            row = fresh.to_dict() or {}
            expires_at = row.get("output_expires_at")
            if not isinstance(expires_at, datetime) or _utc(expires_at) > current:
                return False
            transaction.update(
                snapshot.reference,
                {
                    "state": "payload_expired",
                    "description": firestore.DELETE_FIELD,
                    "completed_at": firestore.DELETE_FIELD,
                    "output_expires_at": firestore.DELETE_FIELD,
                },
            )
            return True

        if _strip_one(transaction):
            stripped += 1
    page = FrameCleanupPage(processed=processed, cleaned=stripped)
    return page if report_page else page.cleaned


def delete_expired_frame_request_metadata(
    uid: str,
    *,
    now: datetime | None = None,
    limit: int = FRAME_REQUEST_MAX_BATCH,
    firestore_client: Any | None = None,
    report_page: bool = False,
) -> int | FrameCleanupPage:
    """Delete expired unattached metadata only after pixel cleanup converges."""

    if not 1 <= limit <= FRAME_REQUEST_MAX_BATCH:
        raise ValueError("limit is outside the bounded frame-request window")
    current = _utc(now or datetime.now(timezone.utc))
    client = _get_client(firestore_client)
    terminal_states = [state.value for state in TERMINAL_FRAME_REQUEST_STATES if state != FrameRequestState.attached]
    safe_cleanup_states = [
        FrameRequestCleanupState.not_required.value,
        FrameRequestCleanupState.deleted.value,
    ]
    query = FRAME_REQUEST_METADATA_EXPIRY_QUERY.build(
        _collection(uid, firestore_client=client),
        {
            "terminal_states": terminal_states,
            "cleanup_states": safe_cleanup_states,
            "now": current,
        },
        field_filter_factory=firestore.FieldFilter,
    ).order_by("expires_at", direction=firestore.Query.ASCENDING)
    processed = deleted = 0
    for snapshot in query.limit(limit).stream():
        processed += 1
        transaction = client.transaction()

        @firestore.transactional
        def _delete_one(transaction: Any) -> bool:
            fresh = snapshot.reference.get(transaction=transaction)
            if not fresh.exists:
                return False
            row = fresh.to_dict() or {}
            expires_at = row.get("expires_at")
            if (
                row.get("state") not in terminal_states
                or row.get("cleanup_state") not in safe_cleanup_states
                or not isinstance(expires_at, datetime)
                or _utc(expires_at) > current
            ):
                return False
            transaction.delete(snapshot.reference)
            return True

        if _delete_one(transaction):
            deleted += 1
    page = FrameCleanupPage(processed=processed, cleaned=deleted)
    return page if report_page else page.cleaned


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
    deleted = 0
    # Page by repeatedly reading a bounded batch and deleting only that page.
    # A hard page fence turns a silent truncation into an error instead of a
    # privacy claim that was only partially fulfilled.
    for _page in range(1000):
        rows = list(
            _collection(uid, firestore_client=client)
            .where(filter=firestore.FieldFilter("conversation_id", "==", conversation_id))
            .limit(batch_size)
            .stream()
        )
        if not rows:
            client.collection(USERS_COLLECTION).document(uid).collection("conversation_keyframe_jobs").document(
                conversation_id
            ).delete()
            return deleted
        batch = client.batch()
        for snapshot in rows:
            batch.delete(snapshot.reference)
            deleted += 1
        batch.commit()
    raise RuntimeError("frame request conversation cleanup exceeded page bound")


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
    seen = 0
    for snapshot in query.limit(limit + 1).stream():
        seen += 1
        if seen > limit:
            raise RuntimeError("frame request storage cleanup was truncated")
        value = (snapshot.to_dict() or {}).get("storage_id")
        if isinstance(value, str) and value.strip() and "/" not in value and "\\" not in value:
            result.append(value.strip())
    return result


def list_all_frame_request_storage_ids(
    uid: str,
    *,
    conversation_id: str | None = None,
    firestore_client: Any | None = None,
    page_size: int = 500,
    max_pages: int = 1000,
) -> list[str]:
    """Exhaustively enumerate opaque storage IDs with a truncation fence."""

    if not 1 <= page_size <= 10000 or not 1 <= max_pages <= 10000:
        raise ValueError("invalid frame-request storage page bounds")
    query_base = _collection(uid, firestore_client=firestore_client)
    if conversation_id is not None:
        if not conversation_id.strip():
            raise ValueError("conversation_id is required")
        query_base = query_base.where(filter=firestore.FieldFilter("conversation_id", "==", conversation_id))
    result: list[str] = []
    last_snapshot: Any | None = None
    for _page in range(max_pages):
        query = query_base.order_by("__name__", direction=firestore.Query.ASCENDING).limit(page_size)
        if last_snapshot is not None:
            query = query.start_after(last_snapshot)
        rows = list(query.stream())
        for snapshot in rows:
            value = (snapshot.to_dict() or {}).get("storage_id")
            if isinstance(value, str) and value.strip() and "/" not in value and "\\" not in value:
                result.append(value.strip())
        if len(rows) < page_size:
            return result
        last_snapshot = rows[-1]
    raise RuntimeError("frame request storage enumeration exceeded page bound")


def list_all_frame_upload_orphan_storage_ids(
    uid: str,
    *,
    firestore_client: Any | None = None,
    page_size: int = 500,
    max_pages: int = 1000,
) -> list[str]:
    """Exhaustively enumerate ambiguous-upload objects for account deletion."""

    if not 1 <= page_size <= 10000 or not 1 <= max_pages <= 10000:
        raise ValueError("invalid frame-upload orphan page bounds")
    collection = _orphan_collection(uid, firestore_client=firestore_client)
    result: list[str] = []
    cursor: Any | None = None
    for _page in range(max_pages):
        query = collection.order_by("__name__", direction=firestore.Query.ASCENDING).limit(page_size)
        if cursor is not None:
            query = query.start_after(cursor)
        rows = list(query.stream())
        for snapshot in rows:
            value = (snapshot.to_dict() or {}).get("storage_id")
            if isinstance(value, str) and value.strip() and "/" not in value and "\\" not in value:
                result.append(value.strip())
        if len(rows) < page_size:
            return result
        cursor = rows[-1]
    raise RuntimeError("frame-upload orphan enumeration exceeded page bound")


def list_all_frame_deletion_outbox_storage_ids(
    uid: str,
    *,
    firestore_client: Any | None = None,
    page_size: int = 500,
    max_pages: int = 1000,
) -> list[str]:
    """Exhaustively enumerate durable conversation-deletion receipts."""

    collection = _deletion_outbox_collection(uid, firestore_client=firestore_client)
    result: list[str] = []
    cursor: Any | None = None
    for _page in range(max_pages):
        query = collection.order_by("__name__", direction=firestore.Query.ASCENDING).limit(page_size)
        if cursor is not None:
            query = query.start_after(cursor)
        rows = list(query.stream())
        for snapshot in rows:
            value = (snapshot.to_dict() or {}).get("storage_id")
            if isinstance(value, str) and value.strip() and "/" not in value and "\\" not in value:
                result.append(value.strip())
        if len(rows) < page_size:
            return result
        cursor = rows[-1]
    raise RuntimeError("frame deletion outbox enumeration exceeded page bound")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
