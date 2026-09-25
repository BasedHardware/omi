"""Typesense keyword index for universal long-term memory atoms (WS-M).

Indexing and search run only for ``layer=long_term``, ``status=active``,
``processing_state=processed`` items.
Users on ``e2ee`` data protection are skipped (same posture as conversation Typesense).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Collection, Dict, List, Optional, cast

from database._client import data_plane_db as default_db_client
from database.memory_vector_metadata import canonical_memory_provider_id
from database.legal_holds import external_write_fence
from models.knowledge_ledger_search import (
    LEDGER_INDEX_VERSION,
    LEDGER_SEARCH_KINDS,
    build_ledger_index_metadata,
    validate_ledger_kinds,
)
from models.memory_evidence import SourceState
from models.product_memory import (
    RESTRICTED_SENSITIVITY_LABELS,
    MemoryItemStatus,
    MemoryLayer,
    ProcessingState,
    MemoryItem,
)
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items
from utils.memory.memory_system import (
    MemorySystem as MemorySystem,  # compatibility export for legacy test doubles
    ensure_canonical_apply_control_state,
    resolve_memory_system as resolve_memory_system,  # compatibility export; user policy is not a UID gate
)

logger = logging.getLogger(__name__)

ATOM_KEYWORD_COLLECTION_ENV = "MEMORY_TYPESENSE_COLLECTION"
MEMORIES_COLLECTION = "canonical_memory_atoms"
TYPESENSE_PROJECTION_READINESS_REQUIRED_ENV = "MEMORY_TYPESENSE_READINESS_REQUIRED"
TYPESENSE_PROJECTION_READINESS_COLLECTION_ENV = "MEMORY_TYPESENSE_READINESS_COLLECTION"
TYPESENSE_PROJECTION_READINESS_SOURCE_SHA_ENV = "MEMORY_TYPESENSE_READINESS_SOURCE_SHA"
TYPESENSE_PROJECTION_READINESS_COLLECTION = "jit_qa_typesense_readiness"
TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID = "jit_qa_projection_readiness"
TYPESENSE_PROJECTION_READINESS_SCHEMA_VERSION = "omi.jit.qa.typesense.readiness.v1"
_DEFAULT_CATEGORY = "interesting"
_REQUIRED_SCHEMA_FIELDS = {
    "memory_id",
    "userId",
    "content",
    "category",
    "layer",
    "status",
    "schema_version",
    "entity_terms",
    "predicate",
    "created_at",
}
_LEDGER_FIELD_DEFINITIONS = {
    "ledger_index_version": {"name": "ledger_index_version", "type": "int32", "facet": True, "optional": True},
    "ledger_schema_version": {"name": "ledger_schema_version", "type": "string", "facet": True, "optional": True},
    "ledger_kind": {"name": "ledger_kind", "type": "string", "facet": True, "optional": True},
    "ledger_row_state": {"name": "ledger_row_state", "type": "string", "facet": True, "optional": True},
    "ledger_has_slot": {"name": "ledger_has_slot", "type": "bool", "facet": True, "optional": True},
    "ledger_subject_scope": {"name": "ledger_subject_scope", "type": "string", "facet": True, "optional": True},
}
_LEDGER_SCHEMA_FIELDS = set(_LEDGER_FIELD_DEFINITIONS)


Payload = Dict[str, Any]


def _payload_or_empty(value: object) -> Payload:
    return cast(Payload, value) if isinstance(value, dict) else {}


def _payload_list(value: object) -> List[Payload]:
    return (
        [cast(Payload, item) for item in cast(List[object], value) if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _typesense_filter_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("`", "\\`")
    return f"`{escaped}`"


def _provider_identity_delete_filter(uid: str, memory_id: str) -> str:
    provider_id = canonical_memory_provider_id(uid, memory_id)
    identity_values = ",".join(_typesense_filter_literal(value) for value in (provider_id, memory_id))
    return f"userId:={_typesense_filter_literal(uid)} && id:=[{identity_values}]"


def _typesense_client() -> Any:
    from utils.conversations.search import client

    return client


def memories_collection_name() -> str:
    return os.getenv(ATOM_KEYWORD_COLLECTION_ENV, MEMORIES_COLLECTION).strip() or MEMORIES_COLLECTION


@dataclass(frozen=True)
class AtomKeywordRebuildReport:
    uid: str
    skipped_reason: Optional[str] = None
    failure_reason: Optional[str] = None
    indexed_count: int = 0
    expected_count: int = 0
    verified: bool = False


class TypesenseProjectionNotReady(RuntimeError):
    """The explicitly gated QA Typesense projection has no trusted readiness epoch."""


def _typesense_projection_readiness_required() -> bool:
    return os.getenv(TYPESENSE_PROJECTION_READINESS_REQUIRED_ENV, "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_typesense_projection_ready(uid: str) -> None:
    """Require a live projection readiness epoch before current-ledger search.

    The QA Typesense service uses an ephemeral data directory.  A restarted
    instance can be healthy while its collection is empty, so the backend
    consumes a marker written after a complete Firestore rebuild and producer
    proof, immediately before the real consumer proof that exercises this
    gate.  A successful qualification still requires the final consumer
    receipt; a process death in that short interval can leave a rebuild-ready
    marker without a qualified receipt, so operators must keep QA execution
    idle while running the proof and retry after an interrupted run.  The
    marker lives in Typesense itself; therefore
    a fresh instance fails closed until the rehydration proof writes a new
    epoch.  Normal services leave the gate unset and retain existing behavior.
    """

    if not _typesense_projection_readiness_required():
        return
    collection_name = os.getenv(TYPESENSE_PROJECTION_READINESS_COLLECTION_ENV, "").strip()
    if not collection_name:
        raise TypesenseProjectionNotReady("Typesense projection readiness collection is not configured")
    try:
        document = (
            _typesense_client()
            .collections[collection_name]
            .documents[TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID]
            .retrieve()
        )
    except Exception as exc:  # noqa: BLE001 - provider errors are one fail-closed boundary
        raise TypesenseProjectionNotReady("Typesense projection readiness marker is unavailable") from exc
    if not isinstance(document, dict):
        raise TypesenseProjectionNotReady("Typesense projection readiness marker is malformed")
    if document.get("id") != TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID:
        raise TypesenseProjectionNotReady("Typesense projection readiness marker has the wrong identity")
    if document.get("userId") != uid:
        raise TypesenseProjectionNotReady("Typesense projection readiness marker has the wrong owner")
    if document.get("readiness_schema_version") != TYPESENSE_PROJECTION_READINESS_SCHEMA_VERSION:
        raise TypesenseProjectionNotReady("Typesense projection readiness marker has the wrong schema")
    epoch = document.get("projection_epoch")
    if not isinstance(epoch, str) or not epoch.strip():
        raise TypesenseProjectionNotReady("Typesense projection readiness marker has no epoch")
    expected_source_sha = os.getenv(TYPESENSE_PROJECTION_READINESS_SOURCE_SHA_ENV, "").strip()
    if expected_source_sha and document.get("source_sha") != expected_source_sha:
        raise TypesenseProjectionNotReady("Typesense projection readiness marker has the wrong source")
    try:
        projection_count = int(document.get("projection_count", 0))
    except (TypeError, ValueError) as exc:
        raise TypesenseProjectionNotReady("Typesense projection readiness marker has an invalid count") from exc
    if projection_count <= 0:
        raise TypesenseProjectionNotReady("Typesense projection readiness marker has no indexed documents")


def is_indexable_long_term_atom(item: MemoryItem) -> bool:
    """Return True when the atom belongs in the durable keyword index."""
    return (
        item.tier == MemoryLayer.long_term
        and item.status == MemoryItemStatus.active
        and item.processing_state == ProcessingState.processed
        and item.source_state == SourceState.active
        and (item.promotion or {}).get("user_review") is not False
        and not set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
        and bool((item.content or "").strip())
    )


def user_allows_atom_keyword_index(uid: str, *, db_client: Any = None) -> bool:
    """Return whether the universal account may use the keyword projection.

    Indexing remains opt-out for E2EE accounts, matching the conversation
    Typesense policy.  There is no UID entitlement/cohort branch.
    """
    if not uid.strip():
        return False
    client = db_client if db_client is not None else default_db_client
    user_doc: Any = client.document(f"users/{uid}").get()
    user_data = _payload_or_empty(user_doc.to_dict() if getattr(user_doc, "exists", False) else {})
    return user_data.get("data_protection_level", "enhanced") != "e2ee"


def _created_at_epoch(item: MemoryItem) -> int:
    captured = item.captured_at
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    return int(captured.timestamp())


def _entity_terms_for_item(item: MemoryItem) -> str:
    """Flatten any structured hints on the item into searchable tokens."""
    terms: List[str] = []
    subject_entity_id = getattr(item, "subject_entity_id", None)
    if isinstance(subject_entity_id, str) and subject_entity_id.strip():
        terms.append(subject_entity_id.strip())
    arguments = _payload_or_empty(getattr(item, "arguments", None))
    terms.extend(str(value).strip() for value in arguments.values() if str(value).strip())
    promotion = _payload_or_empty(item.promotion)
    for key in ("entity", "entity_name", "subject"):
        value = promotion.get(key)
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
    aliases = promotion.get("aliases")
    if isinstance(aliases, list):
        terms.extend(str(alias).strip() for alias in cast(List[object], aliases) if str(alias).strip())
    return " ".join(dict.fromkeys(terms))


def _predicate_for_item(item: MemoryItem) -> str:
    predicate = getattr(item, "predicate", None)
    if isinstance(predicate, str) and predicate.strip():
        return predicate.strip()
    promotion = _payload_or_empty(item.promotion)
    promotion_predicate = promotion.get("predicate")
    return promotion_predicate.strip() if isinstance(promotion_predicate, str) else ""


def build_atom_keyword_document(item: MemoryItem) -> Dict[str, Any]:
    """Build a Typesense document for one indexable long-term atom."""
    document = {
        "id": canonical_memory_provider_id(item.uid, item.memory_id),
        "memory_id": item.memory_id,
        "userId": item.uid,
        "content": item.content or "",
        "category": _DEFAULT_CATEGORY,
        "layer": MemoryLayer.long_term.value,
        "status": MemoryItemStatus.active.value,
        "schema_version": 1,
        "entity_terms": _entity_terms_for_item(item),
        "predicate": _predicate_for_item(item),
        "created_at": _created_at_epoch(item),
    }
    # Generic atom rows remain backwards compatible.  Ledger rows carry an
    # explicit version/state discriminator so a ledger query never treats an
    # unlabelled legacy Typesense hit as canonical ledger evidence.
    document.update(build_ledger_index_metadata(item))
    return document


def merge_memory_search_ids(keyword_ids: List[str], vector_ids: List[str]) -> List[str]:
    """Merge keyword and vector memory ids, keyword hits first, deduplicated."""
    return list(keyword_ids) + [memory_id for memory_id in vector_ids if memory_id not in keyword_ids]


def ensure_memories_collection() -> None:
    """Create the canonical atom Typesense collection when missing (idempotent)."""
    collection_name = memories_collection_name()
    try:
        schema = _payload_or_empty(_typesense_client().collections[collection_name].retrieve())
    except Exception:
        schema = {
            "name": collection_name,
            "fields": [
                {"name": "memory_id", "type": "string"},
                {"name": "userId", "type": "string", "facet": True},
                {"name": "content", "type": "string"},
                {"name": "category", "type": "string", "facet": True, "optional": True},
                {"name": "layer", "type": "string", "facet": True},
                {"name": "status", "type": "string", "facet": True},
                {"name": "schema_version", "type": "int32", "facet": True},
                {"name": "entity_terms", "type": "string", "optional": True},
                {"name": "predicate", "type": "string", "optional": True},
                *[dict(field) for field in _LEDGER_FIELD_DEFINITIONS.values()],
                {"name": "created_at", "type": "int64"},
            ],
            "default_sorting_field": "created_at",
        }
        _typesense_client().collections.create(schema)
        return

    actual_fields = {str(field.get("name")) for field in _payload_list(schema.get("fields")) if field.get("name")}
    missing = sorted(_REQUIRED_SCHEMA_FIELDS - actual_fields)
    if missing:
        raise RuntimeError(
            f"Typesense collection {collection_name!r} is incompatible with canonical memory atoms; "
            f"missing fields: {missing}"
        )


def _schema_field_names(schema: Payload) -> set[str]:
    return {str(field.get("name")) for field in _payload_list(schema.get("fields")) if field.get("name")}


def ensure_ledger_keyword_schema() -> None:
    """Adopt the ledger index fields on a pre-ledger collection; fail closed otherwise.

    ``ensure_memories_collection`` includes the ledger fields only when it
    creates the collection, so a collection created before those fields
    existed could never pass this check: every ledger keyword search failed
    closed, permanently (observed hourly in dev since 2026-08-30). The fields
    are all optional and additive, so adopting them is a bounded idempotent
    alter. A concurrent adopter can win the race; the post-alter re-read is
    the authority, and a collection still missing fields after the attempt
    keeps failing closed.
    """

    collection_name = memories_collection_name()
    collection = _typesense_client().collections[collection_name]
    try:
        schema = _payload_or_empty(collection.retrieve())
    except Exception as exc:
        raise RuntimeError("ledger keyword schema unavailable") from exc
    missing = sorted(_LEDGER_SCHEMA_FIELDS - _schema_field_names(schema))
    if not missing:
        return
    try:
        collection.update({"fields": [dict(_LEDGER_FIELD_DEFINITIONS[name]) for name in missing]})
    except Exception:
        logger.warning(
            "ledger keyword schema adoption failed for collection=%s missing=%s",
            collection_name,
            missing,
        )
    try:
        schema = _payload_or_empty(collection.retrieve())
    except Exception as exc:
        raise RuntimeError("ledger keyword schema unavailable") from exc
    missing = sorted(_LEDGER_SCHEMA_FIELDS - _schema_field_names(schema))
    if missing:
        raise RuntimeError(f"Typesense ledger keyword schema is missing fields: {missing}")


def upsert_atom_keyword_doc(item: MemoryItem, *, db_client: Any = None) -> bool:
    """Upsert one long-term atom when indexable; no-op otherwise."""
    try:
        ensure_canonical_apply_control_state(
            item.uid,
            db_client=db_client if db_client is not None else default_db_client,
        )
    except Exception:
        logger.warning("upsert_atom_keyword_doc blocked by canonical state uid=%s", item.uid)
        return False
    if not user_allows_atom_keyword_index(item.uid, db_client=db_client):
        return False
    if not is_indexable_long_term_atom(item):
        return False
    try:
        client = db_client if db_client is not None else default_db_client
        with external_write_fence(item.uid, firestore_client=client):
            ensure_memories_collection()
            if item.ledger_schema_version == "knowledge_ledger.v1":
                ensure_ledger_keyword_schema()
            doc = build_atom_keyword_document(item)
            documents = _typesense_client().collections[memories_collection_name()].documents
            # The fence refuses this provider write while explicit/account
            # deletion owns the account gate; a stale rebuild cannot upsert
            # after privacy cleanup reports success.
            documents.delete({"filter_by": _provider_identity_delete_filter(item.uid, item.memory_id)})
            documents.upsert(doc)
        return True
    except Exception as exc:
        logger.warning(
            "upsert_atom_keyword_doc failed uid=%s memory_id=%s: %s",
            item.uid,
            item.memory_id,
            exc,
        )
        return False


def delete_atom_keyword_doc(uid: str, memory_id: str, *, db_client: Any = None) -> bool:
    """Remove one keyword doc and report whether the desired absence was confirmed."""
    if not uid or not memory_id:
        return False
    try:
        _typesense_client().collections[memories_collection_name()].documents.delete(
            {"filter_by": _provider_identity_delete_filter(uid, memory_id)}
        )
        return True
    except Exception as exc:
        # Keep this optional projection module importable for callers that do
        # not use Typesense. Some lightweight runtimes and tests intentionally
        # provide only a top-level ``typesense`` placeholder.
        try:
            from typesense.exceptions import ObjectNotFound
        except ImportError:
            object_not_found_type = None
        else:
            object_not_found_type = ObjectNotFound
        if object_not_found_type is not None and isinstance(exc, object_not_found_type):
            return True
        logger.warning("delete_atom_keyword_doc failed uid=%s memory_id=%s: %s", uid, memory_id, exc)
        return False


def purge_user_atom_keyword_index(
    uid: str, *, db_client: Any = None, force: bool = False, raise_on_failure: bool = False
) -> int:
    """Delete all keyword docs for a canonical user. Returns deleted count when available."""
    if not force and not user_allows_atom_keyword_index(uid, db_client=db_client):
        return 0
    try:
        result = _payload_or_empty(
            _typesense_client()
            .collections[memories_collection_name()]
            .documents.delete({"filter_by": f"userId:={_typesense_filter_literal(uid)}"})
        )
        return int(result.get("num_deleted") or 0)
    except Exception as exc:
        logger.warning("purge_user_atom_keyword_index failed uid=%s: %s", uid, exc)
        if raise_on_failure:
            raise
        return 0


def sync_atom_keyword_index_for_item(item: MemoryItem, *, db_client: Any = None) -> bool:
    """Index or purge one atom based on its current authoritative state."""
    if not user_allows_atom_keyword_index(item.uid, db_client=db_client):
        # A policy change can revoke eligibility after this atom was indexed.
        # Exact deletion is therefore required; treating revocation as a
        # successful no-op would leave the prior provider document readable.
        return delete_atom_keyword_doc(item.uid, item.memory_id, db_client=db_client)
    if is_indexable_long_term_atom(item):
        return upsert_atom_keyword_doc(item, db_client=db_client)
    return delete_atom_keyword_doc(item.uid, item.memory_id, db_client=db_client)


def keyword_search_memory_ids(
    uid: str,
    query: str,
    *,
    limit: int = 5,
    start_date: Optional[int] = None,
    end_date: Optional[int] = None,
    db_client: Any = None,
) -> List[str]:
    """Typesense keyword search returning memory ids for hybrid retrieval.

    Fail-open: any search error returns [] so callers can fall back to vector-only results.
    """
    if not user_allows_atom_keyword_index(uid, db_client=db_client):
        return []
    if not (query or "").strip():
        return []
    try:
        filter_by = (
            f"userId:={_typesense_filter_literal(uid)} && layer:={MemoryLayer.long_term.value} "
            f"&& status:={MemoryItemStatus.active.value} && schema_version:=1"
        )
        if start_date is not None:
            filter_by = filter_by + f" && created_at:>={start_date}"
        if end_date is not None:
            filter_by = filter_by + f" && created_at:<={end_date}"

        search_parameters = {
            "q": query,
            "query_by": "content,entity_terms,predicate",
            "filter_by": filter_by,
            "sort_by": "created_at:desc",
            "per_page": max(1, min(limit, 60)),
            "page": 1,
        }
        results = _payload_or_empty(
            _typesense_client().collections[memories_collection_name()].documents.search(search_parameters)
        )
        memory_ids: List[str] = []
        for hit in _payload_list(results.get("hits")):
            doc = _payload_or_empty(hit.get("document"))
            memory_id = doc.get("memory_id") or doc.get("id")
            if memory_id:
                memory_ids.append(str(memory_id))
        return memory_ids
    except Exception as exc:
        logger.warning("keyword_search_memory_ids failed uid=%s, falling back to vector-only: %s", uid, exc)
        return []


def keyword_search_ledger_memory_ids(
    uid: str,
    query: str,
    *,
    kinds: Collection[str] = LEDGER_SEARCH_KINDS,
    limit: int = 5,
    db_client: Any = None,
) -> List[str]:
    """Search only open ledger rows through the versioned keyword projection.

    Older generic atom collections may not have the ledger fields.  Returning
    no keyword candidates in that state is intentional: an unlabelled
    provider document must never be promoted to canonical ledger evidence.
    """

    parsed_kinds = validate_ledger_kinds(kinds)
    if not user_allows_atom_keyword_index(uid, db_client=db_client) or not (query or "").strip():
        return []
    try:
        ensure_ledger_keyword_schema()
        filter_by = (
            f"userId:={_typesense_filter_literal(uid)} && layer:={MemoryLayer.long_term.value} "
            f"&& status:={MemoryItemStatus.active.value} && schema_version:=1 "
            f"&& ledger_index_version:={LEDGER_INDEX_VERSION} "
            "&& ledger_schema_version:=`knowledge_ledger.v1` "
            "&& ledger_row_state:=`open` "
            f"&& ledger_kind:=[{','.join(_typesense_filter_literal(kind) for kind in sorted(parsed_kinds))}]"
        )
        results = _payload_or_empty(
            _typesense_client()
            .collections[memories_collection_name()]
            .documents.search(
                {
                    "q": query,
                    "query_by": "content,entity_terms,predicate",
                    "filter_by": filter_by,
                    "sort_by": "created_at:desc",
                    "per_page": max(1, min(limit, 60)),
                    "page": 1,
                }
            )
        )
        memory_ids: List[str] = []
        for hit in _payload_list(results.get("hits")):
            doc = _payload_or_empty(hit.get("document"))
            memory_id = doc.get("memory_id") or doc.get("id")
            if memory_id:
                memory_ids.append(str(memory_id))
        return memory_ids
    except Exception as exc:
        logger.warning("ledger keyword search failed closed uid=%s error_type=%s", uid, type(exc).__name__)
        return []


def rebuild_atom_keyword_index(uid: str, *, db_client: Any = None) -> AtomKeywordRebuildReport:
    """Rebuild the keyword index for one user from the canonical store (idempotent)."""
    client = db_client if db_client is not None else default_db_client
    try:
        ensure_canonical_apply_control_state(uid, db_client=client)
    except Exception:
        return AtomKeywordRebuildReport(uid=uid, failure_reason="canonical_state_unavailable")
    is_indexable_user = user_allows_atom_keyword_index(uid, db_client=client)
    try:
        # Purge first and fail closed. A rebuild is also the repair path for
        # rows that became restricted, lost source authority, or whose account
        # policy was changed after their content reached Typesense.
        purge_user_atom_keyword_index(
            uid,
            db_client=client,
            force=True,
            raise_on_failure=True,
        )
    except Exception:
        logger.exception("rebuild_atom_keyword_index purge failed uid=%s", uid)
        return AtomKeywordRebuildReport(uid=uid, failure_reason="purge_failed")

    if not is_indexable_user:
        return AtomKeywordRebuildReport(
            uid=uid,
            skipped_reason="not_indexable_user",
            verified=True,
        )

    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    indexable = [item for item in items if is_indexable_long_term_atom(item)]

    indexed = 0
    for item in indexable:
        if upsert_atom_keyword_doc(item, db_client=client):
            indexed += 1

    expected = len(indexable)
    return AtomKeywordRebuildReport(
        uid=uid,
        indexed_count=indexed,
        expected_count=expected,
        verified=indexed == expected,
        failure_reason=None if indexed == expected else "upsert_failed",
    )


def typesense_configured() -> bool:
    """Return True when Typesense env vars are present."""
    return bool(os.getenv("TYPESENSE_HOST") and os.getenv("TYPESENSE_API_KEY"))
