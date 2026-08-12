"""Shared hard-cutover rotation flow for API key credentials.

MCP and Developer keys share one rotation contract, so they share one
implementation: read the document, verify ownership, validate the stored hash,
tombstone the retired hash and evict its cache entry strictly, generate the new
secret, swap it in, and return a strictly parsed projection. Each credential
type supplies only the parts that genuinely differ, as a `ApiKeyRotationKind`.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple, Type, cast

from pydantic import BaseModel

from database.read_boundary import parse_snapshot_strict
from database.api_key_metadata import (
    ApiKeyNotFoundError,
    ApiKeyRevocationUnavailableError,
    is_valid_api_key_hash,
    project_api_key_metadata,
)


@dataclass(frozen=True)
class ApiKeyRotationKind:
    """The credential-type-specific parts of the shared rotation flow.

    `label` prefixes every raised error message, `retire_hash` and
    `delete_cached` are the strict Redis operations for this credential type,
    `generate` issues the replacement secret, `resolve_app_id` derives the app
    identity written back to the document, and `projects_app_id` says whether
    the returned model carries that identity.
    """

    label: str
    collection: str
    firestore_client: Any
    model: Type[BaseModel]
    key_kind: str
    retire_hash: Callable[[str], Any]
    delete_cached: Callable[[str], Any]
    generate: Callable[[], Tuple[str, str, str]]
    resolve_app_id: Callable[[Dict[str, Any]], str]
    normalize_scopes: Callable[[object], Optional[list[str]]]
    projects_app_id: bool = False


def rotate_api_key_secret(kind: ApiKeyRotationKind, user_id: str, key_id: str) -> Tuple[str, Any]:
    """Issue a new secret for an existing key, preserving its identity.

    Rotation is a hard cutover with no grace window: the previous secret stops
    authorizing the moment the swap commits. The retired hash is tombstoned before
    its cache entry is deleted, because deleting alone loses the race — an
    authentication that already read the pre-swap document can write the retired
    hash back into the cache afterwards. The tombstone outlives the cache TTL and
    the authentication path refuses to honor a fenced entry, so a rotated-away
    secret cannot be re-cached into validity. Name, app identity, scopes, creation
    time, and the key's memory grant are carried over unchanged; only the
    credential changes.
    """
    key_ref = kind.firestore_client.collection(kind.collection).document(key_id)
    key_doc = key_ref.get()
    if not getattr(key_doc, "exists", False):
        raise ApiKeyNotFoundError(f"{kind.label} not found")
    raw: object = key_doc.to_dict()
    key_data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    if key_data.get("user_id") != user_id:
        raise ApiKeyNotFoundError(f"{kind.label} not found")

    previous_hashed_key = key_data.get("hashed_key")
    if not is_valid_api_key_hash(previous_hashed_key):
        raise ApiKeyRevocationUnavailableError(f"{kind.label} credential metadata is invalid")
    try:
        fenced = kind.retire_hash(cast(str, previous_hashed_key))
    except Exception as exc:
        raise ApiKeyRevocationUnavailableError(f"{kind.label} rotation fence failed") from exc
    if fenced is not True:
        raise ApiKeyRevocationUnavailableError(f"{kind.label} rotation fence was not confirmed")
    try:
        cache_deleted = kind.delete_cached(cast(str, previous_hashed_key))
    except Exception as exc:
        raise ApiKeyRevocationUnavailableError(f"{kind.label} cache invalidation failed") from exc
    if cache_deleted is not True:
        raise ApiKeyRevocationUnavailableError(f"{kind.label} cache invalidation was not confirmed")

    raw_key, hashed_key, key_prefix = kind.generate()
    now = datetime.now(timezone.utc)
    app_id = kind.resolve_app_id(key_data)
    scopes = kind.normalize_scopes(key_data.get("scopes"))
    key_ref.update(
        {
            "id": key_id,
            "hashed_key": hashed_key,
            "key_prefix": key_prefix,
            "app_id": app_id,
            "scopes": scopes,
            "rotated_at": now,
            "last_used_at": None,
        }
    )

    projection = project_api_key_metadata(
        document_id=key_id,
        raw={**key_data, "key_prefix": key_prefix, "id": key_id},
        snapshot_create_time=getattr(key_doc, "create_time", None),
        key_kind=kind.key_kind,
    )
    projected = projection.metadata
    if kind.projects_app_id:
        projected["app_id"] = app_id
    projected["scopes"] = scopes
    projected["last_used_at"] = None
    # Credential rotation is correctness-critical, so the repaired projection
    # goes through the strict shared read boundary rather than a direct parse.
    return raw_key, parse_snapshot_strict(kind.model, key_doc, payload_from_snapshot=lambda _snapshot: projected)
