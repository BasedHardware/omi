"""Server-owned memory `/v3` compatibility projection reader (WS-G7).

This reader is intentionally fenced and server-only. It reads the memory-derived
compatibility projection state/items paths, validates generation/commit/fence and
convergence invariants, materializes MemoryDB-compatible dictionaries, and fails
closed on any invalid projection page. It performs no writes, calls no vector or
provider services, reads no live ``memory_items`` documents, imports no routers,
and never falls back to the legacy reader.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NoReturn, cast

from google.cloud import firestore

from database.memory_collections import MemoryCollections
from utils.memory.v3.projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3_COMPATIBILITY_PROJECTION_SOURCE,
    V3_COMPATIBILITY_PROJECTION_VERSION,
    V3ProjectionCursor,
    V3ProjectionFailureReason,
    V3ProjectionPage,
    V3ProjectionReadError,
    V3ProjectionReadRequest,
    V3ProjectionState,
)

_MAX_LIMIT = 500
_DOCUMENT_ID_ORDER = "__name__"


def _fail(reason: V3ProjectionFailureReason) -> NoReturn:
    raise V3ProjectionReadError(reason)


def _as_dict(snapshot: Any) -> dict[str, Any] | None:
    if snapshot is None or getattr(snapshot, "exists", False) is False:
        return None
    raw: object = snapshot.to_dict()
    return cast(dict[str, Any], raw) if isinstance(raw, dict) else None


def _int_field(data: dict[str, Any], field: str, reason: V3ProjectionFailureReason) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(reason)
    return value


def _str_field(data: dict[str, Any], field: str, reason: V3ProjectionFailureReason) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        _fail(reason)
    return value


def _validate_state(data: dict[str, Any] | None, request: V3ProjectionReadRequest) -> V3ProjectionState:
    if data is None:
        _fail(V3ProjectionFailureReason.MISSING_PROJECTION_STATE)
    if not isinstance(cast(object, data), dict):
        _fail(V3ProjectionFailureReason.MALFORMED_PROJECTION_STATE)
    if data.get("schema_version") != V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION:
        _fail(V3ProjectionFailureReason.UNSUPPORTED_PROJECTION_SCHEMA)
    if data.get("ready") is not True:
        _fail(V3ProjectionFailureReason.PROJECTION_NOT_READY)
    if data.get("uid") != request.uid:
        _fail(V3ProjectionFailureReason.UID_MISMATCH)
    if data.get("source") != V3_COMPATIBILITY_PROJECTION_SOURCE:
        _fail(V3ProjectionFailureReason.SOURCE_MISMATCH)

    account_generation = _int_field(data, "account_generation", V3ProjectionFailureReason.ACCOUNT_GENERATION_MISMATCH)
    projection_generation = _int_field(data, "projection_generation", V3ProjectionFailureReason.FENCE_MISMATCH)
    if account_generation != request.expected_account_generation:
        _fail(V3ProjectionFailureReason.ACCOUNT_GENERATION_MISMATCH)

    freshness_fence_generation = _int_field(
        data, "freshness_fence_generation", V3ProjectionFailureReason.FENCE_MISMATCH
    )
    tombstone_fence_generation = _int_field(
        data, "tombstone_fence_generation", V3ProjectionFailureReason.FENCE_MISMATCH
    )
    vector_cleanup_fence_generation = _int_field(
        data, "vector_cleanup_fence_generation", V3ProjectionFailureReason.FENCE_MISMATCH
    )
    if (
        freshness_fence_generation != projection_generation
        or tombstone_fence_generation != projection_generation
        or vector_cleanup_fence_generation != projection_generation
    ):
        _fail(V3ProjectionFailureReason.FENCE_MISMATCH)

    source_commit_id = _str_field(data, "source_commit_id", V3ProjectionFailureReason.FENCE_MISMATCH)
    projection_commit_id = _str_field(data, "projection_commit_id", V3ProjectionFailureReason.FENCE_MISMATCH)
    source_evidence_fence = _str_field(data, "source_evidence_fence", V3ProjectionFailureReason.FENCE_MISMATCH)
    projection_evidence_fence = _str_field(data, "projection_evidence_fence", V3ProjectionFailureReason.FENCE_MISMATCH)
    if source_evidence_fence != projection_evidence_fence:
        _fail(V3ProjectionFailureReason.FENCE_MISMATCH)
    if not str(projection_commit_id).startswith("commit-"):
        _fail(V3ProjectionFailureReason.FENCE_MISMATCH)
    if data.get("projection_version") != V3_COMPATIBILITY_PROJECTION_VERSION:
        _fail(V3ProjectionFailureReason.FENCE_MISMATCH)
    if not data.get("source_version"):
        _fail(V3ProjectionFailureReason.FENCE_MISMATCH)
    if (
        data.get("write_convergence_complete") is not True
        or data.get("delete_convergence_complete") is not True
        or data.get("tombstone_convergence_complete") is not True
    ):
        _fail(V3ProjectionFailureReason.INCOMPLETE_CONVERGENCE)

    if request.cursor is not None:
        if (
            request.cursor.account_generation != account_generation
            or request.cursor.projection_generation != projection_generation
            or request.cursor.projection_commit_id != projection_commit_id
        ):
            _fail(V3ProjectionFailureReason.CURSOR_MISMATCH)

    return V3ProjectionState(
        uid=request.uid,
        account_generation=account_generation,
        projection_generation=projection_generation,
        source_commit_id=source_commit_id,
        source_version=str(data.get("source_version")),
        projection_commit_id=projection_commit_id,
        projection_version=str(data.get("projection_version")),
        source_evidence_fence=source_evidence_fence,
        projection_evidence_fence=projection_evidence_fence,
        freshness_fence_generation=freshness_fence_generation,
        tombstone_fence_generation=tombstone_fence_generation,
        vector_cleanup_fence_generation=vector_cleanup_fence_generation,
        empty_projection=data.get("empty_projection") is True,
    )


def _validate_item_fences(item: dict[str, Any], memory_id: str, state: V3ProjectionState) -> bool:
    if item.get("deleted") is True or item.get("tombstoned") is True:
        return False
    if item.get("archive") is True:
        return False
    if item.get("short_term_stale") is True:
        return False
    if item.get("uid") != state.uid or item.get("memory_id") not in (None, memory_id):
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if item.get("schema_version") != V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION:
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if item.get("source") != V3_COMPATIBILITY_PROJECTION_SOURCE:
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if item.get("account_generation") != state.account_generation:
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if item.get("projection_generation") != state.projection_generation:
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if item.get("source_commit_id") != state.source_commit_id:
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if item.get("projection_commit_id") != state.projection_commit_id:
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if item.get("projection_evidence_fence") != state.projection_evidence_fence:
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if item.get("freshness_fence_generation") != state.freshness_fence_generation:
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if item.get("tombstone_fence_generation") != state.tombstone_fence_generation:
        _fail(V3ProjectionFailureReason.ITEM_FENCE_MISMATCH)
    if (
        item.get("write_convergence_complete") is not True
        or item.get("delete_convergence_complete") is not True
        or item.get("tombstone_convergence_complete") is not True
    ):
        _fail(V3ProjectionFailureReason.INCOMPLETE_CONVERGENCE)
    return True


def _memory_payload(item: dict[str, Any], memory_id: str, state: V3ProjectionState) -> dict[str, Any]:
    if not _validate_item_fences(item, memory_id, state):
        return {}
    payload = item.get("memorydb")
    if not isinstance(payload, dict):
        _fail(V3ProjectionFailureReason.INVALID_PROJECTION_PAYLOAD)
    payload = dict(cast(dict[str, Any], payload))
    payload.setdefault("id", memory_id)
    payload.setdefault("uid", state.uid)
    required_fields = {
        "id",
        "uid",
        "content",
        "category",
        "visibility",
        "tags",
        "created_at",
        "updated_at",
        "reviewed",
        "user_review",
        "manually_added",
        "edited",
        "conversation_id",
        "data_protection_level",
    }
    forbidden_memory_fields = {
        "generation",
        "source_commit_id",
        "source_version",
        "projection_commit_id",
        "projection_version",
        "projection_freshness_fence",
        "archive_tier",
        "short_term_staleness_reason",
    }
    if not required_fields.issubset(payload):
        _fail(V3ProjectionFailureReason.INVALID_PROJECTION_PAYLOAD)
    if forbidden_memory_fields.intersection(payload):
        _fail(V3ProjectionFailureReason.INVALID_PROJECTION_PAYLOAD)
    if payload.get("id") != memory_id or payload.get("uid") != state.uid:
        _fail(V3ProjectionFailureReason.INVALID_PROJECTION_PAYLOAD)
    if not isinstance(payload.get("content"), str) or not payload.get("content"):
        _fail(V3ProjectionFailureReason.INVALID_PROJECTION_PAYLOAD)
    if not isinstance(payload.get("tags"), list):
        _fail(V3ProjectionFailureReason.INVALID_PROJECTION_PAYLOAD)
    if not isinstance(payload.get("created_at"), datetime) or not isinstance(payload.get("updated_at"), datetime):
        _fail(V3ProjectionFailureReason.INVALID_PROJECTION_PAYLOAD)
    return payload


def _apply_query_order(query: Any) -> Any:
    try:
        document_id_field = firestore.FieldPath.document_id()  # type: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType]  # firestore.FieldPath absent from stubs; runtime-guarded by except fallback to "__name__"
    except AttributeError:
        document_id_field = _DOCUMENT_ID_ORDER
    return query.order_by("created_at", direction=firestore.Query.DESCENDING).order_by(
        document_id_field, direction=firestore.Query.DESCENDING
    )


def _apply_cursor(query: Any, cursor: V3ProjectionCursor | None) -> Any:
    if cursor is None:
        return query
    return query.start_after({"created_at": cursor.created_at, _DOCUMENT_ID_ORDER: cursor.memory_id})


def _validate_request(request: V3ProjectionReadRequest) -> None:
    if request.offset is not None:
        _fail(V3ProjectionFailureReason.OFFSET_UNSUPPORTED)
    if request.limit < 1 or request.limit > _MAX_LIMIT:
        _fail(V3ProjectionFailureReason.LIMIT_OUT_OF_RANGE)


def read_v3_compatibility_projection_page(
    *, db_client: firestore.Client, request: V3ProjectionReadRequest
) -> V3ProjectionPage:
    _validate_request(request)
    paths = MemoryCollections(uid=request.uid)
    state_snapshot = db_client.document(paths.v3_compatibility_projection_state).get()  # type: ignore[reportUnknownMemberType]  # firestore DocumentReference.get stub has unknown transaction param
    state = _validate_state(_as_dict(state_snapshot), request)

    query = db_client.collection(paths.v3_compatibility_projection_items)
    query = _apply_cursor(_apply_query_order(query), request.cursor)
    snapshots = list(query.limit(request.limit + 1).stream())

    items: list[dict[str, Any]] = []
    last_visible: tuple[datetime, str] | None = None
    for snapshot in snapshots:
        item = _as_dict(snapshot)
        if item is None:
            _fail(V3ProjectionFailureReason.INVALID_PROJECTION_PAYLOAD)
        payload = _memory_payload(item, snapshot.id, state)
        if payload:
            items.append(payload)
            last_visible = (payload["created_at"], payload["id"])
        if len(items) == request.limit:
            break

    next_cursor: V3ProjectionCursor | None = None
    if len(snapshots) > request.limit and last_visible is not None:
        next_cursor = V3ProjectionCursor(
            created_at=last_visible[0],
            memory_id=last_visible[1],
            account_generation=state.account_generation,
            projection_generation=state.projection_generation,
            projection_commit_id=state.projection_commit_id,
        )

    return V3ProjectionPage(
        items=items,
        next_cursor=next_cursor,
        account_generation=state.account_generation,
        projection_generation=state.projection_generation,
        source_commit_id=state.source_commit_id,
        source_version=state.source_version,
        projection_commit_id=state.projection_commit_id,
        projection_version=state.projection_version,
        empty_projection=state.empty_projection and not items,
    )


__all__ = ["read_v3_compatibility_projection_page"]
