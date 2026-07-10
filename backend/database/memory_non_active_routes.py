"""Canonical non-active memory route persistence (WS-G7)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from google.cloud.firestore_v1 import transactional
except ImportError:  # pragma: no cover - local unit tests mock Firestore.

    def transactional(func):
        def wrapper(transaction, *args, **kwargs):
            if hasattr(transaction, "_begin"):
                transaction._begin()
            try:
                result = func(transaction, *args, **kwargs)
                if hasattr(transaction, "_commit"):
                    transaction._commit()
                return result
            except Exception:
                if hasattr(transaction, "_rollback"):
                    transaction._rollback()
                raise
            finally:
                if hasattr(transaction, "_clean_up"):
                    transaction._clean_up()

        return wrapper


from pydantic import BaseModel, ConfigDict, Field, field_validator

from database._client import db
from database.memory_collections import MemoryCollections


class NonActiveRoute(str, Enum):
    review = "review"
    archive = "archive"
    context_only = "context_only"
    reject = "reject"
    hidden = "hidden"
    skip = "skip"


class NonActiveRouteStoreConflict(Exception):
    pass


class _NonActiveRouteOutcomeBase(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    uid: str
    route: NonActiveRoute
    idempotency_key: str
    source_ids: List[str]
    reason: str
    run_id: str
    patch_id: Optional[str] = None
    audit_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    default_long_term_visible: bool = False

    @field_validator("uid", "idempotency_key", "reason", "run_id")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("required fields must not be blank")
        return value

    @field_validator("source_ids")
    @classmethod
    def validate_source_ids(cls, value: List[str]) -> List[str]:
        normalized = sorted({source_id.strip() for source_id in value if source_id and source_id.strip()})
        if not normalized:
            raise ValueError("source_ids must not be empty")
        return normalized

    @field_validator("created_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class NonActiveRouteOutcome(_NonActiveRouteOutcomeBase):
    outcome_id: Optional[str] = None
    payload_fingerprint: Optional[str] = None


class PersistedNonActiveRouteOutcome(_NonActiveRouteOutcomeBase):
    outcome_id: str
    payload_fingerprint: str


def persist_non_active_route_outcome(
    outcome: NonActiveRouteOutcome,
    *,
    db_client=db,
) -> PersistedNonActiveRouteOutcome:
    transaction = db_client.transaction()
    return _persist_non_active_route_outcome_transaction(transaction, db_client, outcome)


@transactional
def _persist_non_active_route_outcome_transaction(
    transaction,
    db_client,
    outcome: NonActiveRouteOutcome,
) -> PersistedNonActiveRouteOutcome:
    persisted = _with_persistence_fields(outcome)
    collections = MemoryCollections(uid=persisted.uid)
    outcome_ref = db_client.document(f"{collections.non_active_memory_routes}/{persisted.outcome_id}")
    snapshot = outcome_ref.get(transaction=transaction)
    if snapshot.exists:
        existing = PersistedNonActiveRouteOutcome(**(snapshot.to_dict() or {}))
        if existing.payload_fingerprint != persisted.payload_fingerprint:
            raise NonActiveRouteStoreConflict("idempotency key payload mismatch")
        return existing

    transaction.set(outcome_ref, persisted.model_dump(mode="json"))
    return persisted


def _with_persistence_fields(outcome: NonActiveRouteOutcome) -> PersistedNonActiveRouteOutcome:
    data = outcome.model_dump(mode="python")
    outcome_id = outcome.outcome_id or _stable_outcome_id(outcome.uid, outcome.idempotency_key)
    data["outcome_id"] = outcome_id
    data["default_long_term_visible"] = False
    data["payload_fingerprint"] = _payload_fingerprint(data)
    return PersistedNonActiveRouteOutcome(**data)


def _stable_outcome_id(uid: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{uid}:{idempotency_key}".encode("utf-8")).hexdigest()
    return f"nar_{digest[:32]}"


def _payload_fingerprint(data: Dict[str, Any]) -> str:
    comparable = dict(data)
    comparable.pop("payload_fingerprint", None)
    comparable.pop("created_at", None)
    payload = json.dumps(comparable, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "NonActiveRoute",
    "NonActiveRouteOutcome",
    "NonActiveRouteStoreConflict",
    "PersistedNonActiveRouteOutcome",
    "persist_non_active_route_outcome",
]
