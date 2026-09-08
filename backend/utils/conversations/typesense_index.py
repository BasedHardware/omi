"""First-party Typesense projection of the durable conversation store.

Prod conversation search (`utils.conversations.search`) reads the Typesense
``conversations`` collection. Writes to that collection historically came only
from the Firebase extension ``typesense/firestore-typesense-search`` (instance
``firestore-typesense-conversations``, Cloud Run
``ext-firestore-typesense-conversations-indexonwrite``), which is not part of
this monorepo. This module mirrors that pipe: every durable conversation
write/delete now dual-writes the same projection from the backend, the same
posture the memory keyword index (`utils.memory.atom_keyword_index`) already
has for memories.

Runbook: the Firebase extension is deliberately still installed and still
indexing. This code dual-writes on top of it — documents are keyed by
conversation id and upserted idempotently, so the two writers converge on the
same content. Do NOT uninstall or disable ``firestore-typesense-conversations``
here; removal is a follow-up ops step taken only after this first-party writer
has baked in prod and its coverage has been verified against the extension's
documents.

Field contract — must match what search already queries and what the extension
indexed: ``id, userId, created_at, started_at, finished_at, discarded,
structured, geolocation``. ``transcript_segments`` and per-segment speaker
fields are NOT part of the Typesense schema (Typesense rejects them with 400),
so the projection is a strict allow-list: fields not named above can never
reach Typesense through this module.

E2EE accounts are skipped the same way the atom keyword index skips them, and
a skip deletes any document previously indexed for that conversation so a
policy change cannot leave plaintext readable.

Everything here is fail-open: a Typesense or Firestore read error is logged,
counted, and swallowed. Search indexing must never fail a durable
conversation write.

No per-conversation revision CAS or sync mutex guards these writes: the
Firebase extension still owns production indexing and already races every
first-party write, and Typesense upserts are idempotent per document id.
Serialization is a follow-up for when the extension is removed.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from prometheus_client import Counter

logger = logging.getLogger(__name__)


def _resolve_default_db_client() -> Any:
    # Lazy: `database._client` pulls google-cloud-firestore (~0.6s first-import
    # CPU) that stub-loading test harnesses and Typesense-unconfigured runtimes
    # must not pay. Tests patch this resolver to inject their policy client.
    from database._client import data_plane_db as client

    return client


def _resolve_firestore_client() -> Any:
    from database._client import get_firestore_client as client

    return client


def _record_fallback_helper(component: str, *, from_mode: str, to_mode: str, reason: str) -> None:
    # Lazy: `utils.observability.fallback` pulls fastapi via utils.metrics
    # (~1s first-import CPU) — error paths only.
    from utils.observability.fallback import record_fallback

    record_fallback(
        component=component,
        from_mode=from_mode,
        to_mode=to_mode,
        reason=reason,
        outcome="degraded",
        log=logger,
    )


# The Typesense collection `utils.conversations.search` reads. Hardcoded on
# purpose: an env override here would silently split reads from writes.
CONVERSATION_TYPESENSE_COLLECTION = "conversations"

# Optional kill switch. Unset (or any value other than the disabled set) means
# "on whenever the shared Typesense env (TYPESENSE_HOST / TYPESENSE_API_KEY
# already used by search) is configured", so dual-write starts in every
# environment that can already search — no new secret is required.
CONVERSATION_INDEX_WRITES_ENV = "TYPESENSE_CONVERSATION_INDEX_WRITES"
_DISABLED_VALUES = frozenset({"0", "false", "off", "no"})

# Firestore fields the projection carries. `userId` is derived from the document
# path (as the extension derived it), not stored on the conversation document.
_INDEXED_FIRESTORE_FIELDS = (
    "id",
    "structured",
    "created_at",
    "discarded",
    "started_at",
    "finished_at",
    "geolocation",
)

CONVERSATION_TYPESENSE_INDEX_EVENTS = Counter(
    "omi_conversation_typesense_index_events_total",
    "First-party conversation Typesense projection outcomes by bounded event; never labeled by UID",
    ["event"],
)


def _count(event: str) -> None:
    CONVERSATION_TYPESENSE_INDEX_EVENTS.labels(event=event).inc()


_TRANSIENT_ERROR_MARKERS = (
    "timed out",
    "timeout",
    "connection refused",
    "connection reset",
    "temporarily unavailable",
    "service unavailable",
)


def _record_index_fallback(exc: BaseException) -> None:
    """Fail-open telemetry per the shared fallback contract (`.github/agent-docs/fallback-telemetry.md`)."""
    message = str(exc).lower()
    reason = "timeout" if any(marker in message for marker in _TRANSIENT_ERROR_MARKERS) else "other"
    _record_fallback_helper(
        component="other",
        from_mode="conversation_index_dual_write",
        to_mode="fail_open",
        reason=reason,
    )


def _payload_or_empty(value: object) -> Dict[str, Any]:
    return cast(Dict[str, Any], value) if isinstance(value, dict) else {}


def _typesense_filter_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("`", "\\`")
    return f"`{escaped}`"


def _typesense_client() -> Any:
    # Local import mirrors utils.memory.atom_keyword_index: the shared lazy
    # client seam in utils.conversations.search, which tests replace.
    from utils.conversations.search import client

    return client


def _is_object_not_found(exc: BaseException) -> bool:
    try:
        from typesense.exceptions import ObjectNotFound
    except ImportError:
        object_not_found_type: Optional[type] = None
    else:
        object_not_found_type = ObjectNotFound
    if object_not_found_type is not None and isinstance(exc, object_not_found_type):
        return True
    # Lightweight runtimes and tests provide only a top-level `typesense`
    # placeholder without the exceptions module.
    return type(exc).__module__.endswith("exceptions") and type(exc).__name__ == "ObjectNotFound"


def typesense_configured() -> bool:
    """Return True when the shared Typesense env vars are present."""
    return bool(os.getenv("TYPESENSE_HOST") and os.getenv("TYPESENSE_API_KEY"))


def conversation_index_writes_enabled() -> bool:
    """Return whether first-party conversation index writes should run.

    Default on whenever the shared Typesense env is configured (the same env
    search already requires), so dual-write begins in every environment that
    can already serve conversation search. ``TYPESENSE_CONVERSATION_INDEX_WRITES``
    is an explicit kill switch for that default.
    """
    if not typesense_configured():
        return False
    override = os.getenv(CONVERSATION_INDEX_WRITES_ENV)
    if override is None or not override.strip():
        return True
    return override.strip().lower() not in _DISABLED_VALUES


def user_allows_conversation_index(uid: str, *, db_client: Any = None) -> bool:
    """Return whether the account may use the conversation keyword projection.

    Indexing remains opt-out for E2EE accounts, matching the atom keyword index
    posture. There is no UID entitlement/cohort branch.
    """
    if not uid or not uid.strip():
        return False
    client = db_client if db_client is not None else _resolve_default_db_client()
    user_doc: Any = client.document(f"users/{uid}").get()
    user_data = _payload_or_empty(user_doc.to_dict() if getattr(user_doc, "exists", False) else {})
    return user_data.get("data_protection_level", "enhanced") != "e2ee"


def _epoch_seconds(value: object) -> Optional[int]:
    """Coerce a stored timestamp to unix seconds; None when not derivable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return int(moment.timestamp())
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _geolocation_point(value: object) -> Optional[list[float]]:
    """Coerce a stored geolocation to the Typesense ``[lat, lng]`` shape."""
    latitude: object = getattr(value, "latitude", None)
    longitude: object = getattr(value, "longitude", None)
    if latitude is None and longitude is None and isinstance(value, dict):
        latitude = value.get("latitude")
        longitude = value.get("longitude")
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return None
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return [float(latitude), float(longitude)]
    return None


def build_conversation_index_document(uid: str, conversation_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build the Typesense document for one conversation, or None when unindexable.

    Strict allow-list: only the fields the ``conversations`` collection schema
    declares ever leave this function. ``transcript_segments``, speaker fields,
    photos, and app results cannot be indexed because they are never read.
    """
    conversation_id = str(conversation_data.get("id") or "").strip()
    created_at = _epoch_seconds(conversation_data.get("created_at"))
    if not conversation_id or created_at is None:
        # `created_at` is the collection's default sorting field; a document
        # without it cannot serve the search sort contract.
        return None
    document: Dict[str, Any] = {
        "id": conversation_id,
        "userId": uid,
        "created_at": created_at,
        "discarded": bool(conversation_data.get("discarded", False)),
    }
    started_at = _epoch_seconds(conversation_data.get("started_at"))
    if started_at is not None:
        document["started_at"] = started_at
    finished_at = _epoch_seconds(conversation_data.get("finished_at"))
    if finished_at is not None:
        document["finished_at"] = finished_at
    structured = conversation_data.get("structured")
    if isinstance(structured, dict) and structured:
        document["structured"] = structured
    geolocation = _geolocation_point(conversation_data.get("geolocation"))
    if geolocation is not None:
        document["geolocation"] = geolocation
    return document


def _fetch_index_projection(
    uid: str, conversation_id: str, *, firestore_client: Any = None
) -> Optional[Dict[str, Any]]:
    """Read only the indexed fields of one conversation document.

    The extension re-synced the whole Firestore document on every write; this
    is the bounded equivalent. Returns None when the document is gone, which
    routes the caller to an index delete (write-after-delete self-healing).
    """
    client = firestore_client if firestore_client is not None else _resolve_firestore_client()
    snapshot = (
        client.collection("users")
        .document(uid)
        .collection(CONVERSATION_TYPESENSE_COLLECTION)
        .document(conversation_id)
        .get(field_paths=list(_INDEXED_FIRESTORE_FIELDS))
    )
    if not getattr(snapshot, "exists", False):
        return None
    data = _payload_or_empty(snapshot.to_dict())
    data["id"] = conversation_id
    return data


def delete_conversation_index_doc(uid: str, conversation_id: str) -> bool:
    """Remove one conversation from the index; ObjectNotFound counts as done.

    Deliberately not gated on the write flag or the user policy: deletes are
    privacy hygiene and must keep flowing when dual-writes are disabled.
    """
    if not uid or not conversation_id:
        return False
    if not typesense_configured():
        return False
    try:
        _typesense_client().collections[CONVERSATION_TYPESENSE_COLLECTION].documents[conversation_id].delete()
        _count("deleted")
        return True
    except Exception as exc:
        if _is_object_not_found(exc):
            _count("deleted")
            return True
        _count("error")
        _record_index_fallback(exc)
        logger.warning("conversation Typesense delete failed uid=%s conversation_id=%s: %s", uid, conversation_id, exc)
        return False


def _sync_conversation_index_after_write(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
    db_client: Any = None,
) -> bool:
    if not typesense_configured():
        # No shared Typesense env means no index can exist in this environment
        # (the extension indexes the same env): skip before any Firestore or
        # Typesense I/O. This is distinct from the kill switch below, which
        # keeps privacy deletes flowing against an existing index.
        _count("skipped_unconfigured")
        return False
    if not user_allows_conversation_index(uid, db_client=db_client):
        # A policy change can revoke eligibility after this conversation was
        # indexed (by this writer or by the extension). Exact deletion is
        # therefore required even when upserts are disabled: the kill switch
        # stops indexing, not privacy cleanup.
        _count("skipped_e2ee")
        return delete_conversation_index_doc(uid, conversation_id)
    if not conversation_index_writes_enabled():
        _count("skipped_disabled")
        return False
    try:
        data = _fetch_index_projection(uid, conversation_id, firestore_client=firestore_client)
    except Exception as exc:
        _count("error")
        _record_index_fallback(exc)
        logger.warning(
            "conversation Typesense projection read failed uid=%s conversation_id=%s: %s", uid, conversation_id, exc
        )
        return False
    if data is None:
        # The Firestore document is gone (deleted since the write that queued
        # this sync); converge the index to absence instead of upserting stale
        # content — the race the extension's delete trigger otherwise covered.
        return delete_conversation_index_doc(uid, conversation_id)
    document = build_conversation_index_document(uid, data)
    if document is None:
        _count("skipped_invalid")
        logger.warning(
            "conversation Typesense projection dropped unindexable document uid=%s conversation_id=%s",
            uid,
            conversation_id,
        )
        return False
    try:
        _typesense_client().collections[CONVERSATION_TYPESENSE_COLLECTION].documents.upsert(document)
        _count("upserted")
        return True
    except Exception as exc:
        _count("error")
        _record_index_fallback(exc)
        logger.warning("conversation Typesense upsert failed uid=%s conversation_id=%s: %s", uid, conversation_id, exc)
        return False


def sync_conversation_index_after_write(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
    db_client: Any = None,
) -> bool:
    """Converge the index to the durable state of one conversation after a write.

    Fail-open by contract: this function never raises, so a Typesense outage
    degrades search freshness, never the Firestore write that called it.
    """
    try:
        return _sync_conversation_index_after_write(
            uid, conversation_id, firestore_client=firestore_client, db_client=db_client
        )
    except Exception as exc:
        _count("error")
        _record_index_fallback(exc)
        logger.warning("conversation Typesense sync failed uid=%s conversation_id=%s: %s", uid, conversation_id, exc)
        return False


def purge_user_conversation_index(uid: str, *, raise_on_failure: bool = False) -> int:
    """Delete every indexed conversation for a user. Returns the deleted count.

    Used by the account-deletion wipe. Filter-based, so it stays executable
    even after the Firestore user document is gone.
    """
    if not uid:
        return 0
    if not typesense_configured():
        # A required purge must not report silent success when it never
        # reached the index; only best-effort callers accept the quiet 0.
        if raise_on_failure:
            raise RuntimeError("Typesense env is not configured; conversation index purge cannot be verified")
        return 0
    try:
        result = _payload_or_empty(
            _typesense_client()
            .collections[CONVERSATION_TYPESENSE_COLLECTION]
            .documents.delete({"filter_by": f"userId:={_typesense_filter_literal(uid)}"})
        )
        deleted = int(result.get("num_deleted") or 0)
        _count("purged")
        return deleted
    except Exception as exc:
        _count("error")
        _record_index_fallback(exc)
        logger.warning("purge_user_conversation_index failed uid=%s: %s", uid, exc)
        if raise_on_failure:
            raise
        return 0
