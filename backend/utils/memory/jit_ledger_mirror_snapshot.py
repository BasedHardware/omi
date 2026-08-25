"""Paginated, generation-fenced knowledge-ledger mirror snapshots."""

# LIFECYCLE: permanent

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import time
from typing import Any

from google.cloud import firestore

from database.memory_collections import MemoryCollections
from models.memories import MemoryDB
from models.memory_evidence import (
    ArtifactPreservationState,
    ProvenanceVisibility,
    RedactionStatus,
    SourceState,
)
from models.product_memory import MemoryItem, MemoryItemStatus, memory_item_has_lifecycle_metadata
from utils.memory.canonical_memory_adapter import memory_item_to_memorydb
from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION
from utils.memory.knowledge_ledger_migration import (
    read_ledger_migration_completion,
    read_ledger_prompt_projection_receipt,
)
from utils.memory.universal_list_cursor import UniversalListCursorError, cursor_secret
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation

MIRROR_SCHEMA_VERSION = "knowledge_ledger_mirror.v1"
DEFAULT_MIRROR_PAGE_SIZE = 200
MAX_MIRROR_PAGE_SIZE = 500
MAX_MIRROR_CURSOR_CHARS = 2_048
MIRROR_CURSOR_PREFIX = "jlm"
MIRROR_CURSOR_TTL_SECONDS = 900


@dataclass(frozen=True)
class LedgerMirrorFence:
    owner_id: str
    account_generation: int
    source_generation: int
    writer_epoch: int
    head_commit_id: str
    commit_sequence: int

    @property
    def epoch_id(self) -> str:
        payload = {
            "schema_version": MIRROR_SCHEMA_VERSION,
            "owner_id": self.owner_id,
            "account_generation": self.account_generation,
            "source_generation": self.source_generation,
            "writer_epoch": self.writer_epoch,
            "head_commit_id": self.head_commit_id,
            "commit_sequence": self.commit_sequence,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class LedgerMirrorAlias:
    alias_memory_id: str
    canonical_memory_id: str
    source_memory_id: str
    reason: str


@dataclass(frozen=True)
class LedgerMirrorRow:
    memory_id: str
    item_revision: int
    status: MemoryItemStatus
    source_state: SourceState
    canonical_memory_id: str | None
    content_purged: bool
    memory: MemoryDB | None


@dataclass(frozen=True)
class LedgerMirrorPage:
    fence: LedgerMirrorFence | None
    rows: tuple[LedgerMirrorRow, ...]
    aliases: tuple[LedgerMirrorAlias, ...]
    page_revision: str
    chain_revision: str
    scanned_count: int
    projected_count: int
    next_cursor: str | None
    final_page: bool
    failure_reason: str | None = None


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cursor_signature(payload_segment: str, secret: bytes) -> str:
    return _b64encode(hmac.new(secret, payload_segment.encode("ascii"), hashlib.sha256).digest())


def _encode_cursor(
    *,
    uid: str,
    epoch_id: str,
    last_memory_id: str,
    chain_revision: str,
    scanned_count: int,
    projected_count: int,
    secret: bytes,
    now_epoch_seconds: int | None = None,
) -> str:
    now = int(time.time() if now_epoch_seconds is None else now_epoch_seconds)
    payload = {
        "v": 2,
        "uid": uid,
        "epoch_id": epoch_id,
        "last_memory_id": last_memory_id,
        "chain_revision": chain_revision,
        "scanned_count": scanned_count,
        "projected_count": projected_count,
        "expires_at": now + MIRROR_CURSOR_TTL_SECONDS,
    }
    payload_segment = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return f"{MIRROR_CURSOR_PREFIX}.{payload_segment}.{_cursor_signature(payload_segment, secret)}"


def _decode_cursor(
    cursor: str | None,
    *,
    uid: str,
    secret: bytes,
    now_epoch_seconds: int | None = None,
) -> tuple[str | None, str | None, str, int, int]:
    if cursor is None:
        return None, None, "", 0, 0
    if not cursor or len(cursor) > MAX_MIRROR_CURSOR_CHARS:
        raise ValueError("mirror cursor is invalid")
    parts = cursor.split(".")
    if len(parts) != 3 or parts[0] != MIRROR_CURSOR_PREFIX:
        raise ValueError("mirror cursor is invalid")
    _, payload_segment, signature = parts
    if not hmac.compare_digest(_cursor_signature(payload_segment, secret), signature):
        raise ValueError("mirror cursor signature is invalid")
    try:
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception as exc:
        raise ValueError("mirror cursor is invalid") from exc
    if not isinstance(payload, dict) or payload.get("v") != 2 or payload.get("uid") != uid:
        raise ValueError("mirror cursor version is invalid")
    epoch_id = payload.get("epoch_id")
    last_memory_id = payload.get("last_memory_id")
    chain_revision = payload.get("chain_revision")
    scanned_count = payload.get("scanned_count")
    projected_count = payload.get("projected_count")
    expires_at = payload.get("expires_at")
    now = int(time.time() if now_epoch_seconds is None else now_epoch_seconds)
    if (
        not isinstance(epoch_id, str)
        or len(epoch_id) != 64
        or not isinstance(last_memory_id, str)
        or not last_memory_id.strip()
        or len(last_memory_id) > 256
        or "/" in last_memory_id
        or not isinstance(chain_revision, str)
        or len(chain_revision) != 64
        or type(scanned_count) is not int
        or scanned_count < 1
        or type(projected_count) is not int
        or not 0 <= projected_count <= scanned_count
        or type(expires_at) is not int
        or expires_at < now
    ):
        raise ValueError("mirror cursor payload is invalid")
    return epoch_id, last_memory_id, chain_revision, scanned_count, projected_count


def _read_fence(uid: str, *, db_client: Any) -> LedgerMirrorFence | None:
    completion = read_ledger_migration_completion(uid, db_client=db_client)
    if completion is None:
        return None
    receipt = read_ledger_prompt_projection_receipt(uid, db_client=db_client, completion=completion)
    if receipt is None:
        return None
    trusted = read_memory_v3_trusted_account_generation(uid=uid, db_client=db_client)
    try:
        account_generation = trusted.require_account_generation()
    except Exception:
        return None
    head_commit_id = trusted.head_commit_id or ""
    commit_sequence = trusted.commit_sequence
    if (
        not head_commit_id
        or commit_sequence is None
        or account_generation != receipt.account_generation
        or head_commit_id != receipt.source_head_commit_id
    ):
        return None
    return LedgerMirrorFence(
        owner_id=uid,
        account_generation=account_generation,
        source_generation=receipt.source_generation,
        writer_epoch=receipt.writer_epoch,
        head_commit_id=head_commit_id,
        commit_sequence=commit_sequence,
    )


def _aliases(item: MemoryItem) -> tuple[LedgerMirrorAlias, ...]:
    aliases: list[LedgerMirrorAlias] = []
    for target, reason in (
        (item.canonical_memory_id, "canonical_memory_id"),
        (item.superseded_by, "superseded_by"),
    ):
        normalized = (target or "").strip()
        if not normalized:
            continue
        if normalized == item.memory_id or "/" in normalized or len(normalized) > 256:
            raise ValueError("ledger mirror alias is invalid")
        aliases.append(
            LedgerMirrorAlias(
                alias_memory_id=item.memory_id,
                canonical_memory_id=normalized,
                source_memory_id=item.memory_id,
                reason=reason,
            )
        )
    return tuple(dict.fromkeys(aliases))


def _is_content_free_privacy_tombstone(item: MemoryItem) -> bool:
    if item.status != MemoryItemStatus.tombstoned or item.source_state not in {
        SourceState.tombstoned,
        SourceState.purged,
    }:
        return False
    if (
        (item.content or "").strip()
        or (item.body or "").strip()
        or item.arguments
        or item.trigger_condition
        or memory_item_has_lifecycle_metadata(item)
        or item.ledger_schema_version is not None
        or item.intent_backed
    ):
        return False
    return all(
        not evidence.artifact_refs
        and not evidence.quote_refs
        and evidence.content_hash is None
        and evidence.patch_id is None
        and evidence.commit_id is None
        and evidence.client_device_id is None
        and evidence.source_state in {SourceState.tombstoned, SourceState.purged}
        and evidence.artifact_preservation
        in {ArtifactPreservationState.deleted_by_user, ArtifactPreservationState.account_purged}
        and evidence.provenance_visibility == ProvenanceVisibility.hidden
        and evidence.redaction_status in {RedactionStatus.tombstoned, RedactionStatus.purged}
        and evidence.encryption_or_redaction_status in {RedactionStatus.tombstoned, RedactionStatus.purged}
        for evidence in item.evidence
    )


def _project_row(item: MemoryItem) -> LedgerMirrorRow | None:
    if item.status == MemoryItemStatus.tombstoned or item.source_state in {
        SourceState.tombstoned,
        SourceState.purged,
    }:
        if not _is_content_free_privacy_tombstone(item):
            raise ValueError("deleted ledger mirror row retains content")
        return LedgerMirrorRow(
            memory_id=item.memory_id,
            item_revision=item.item_revision,
            status=item.status,
            source_state=item.source_state,
            canonical_memory_id=(item.canonical_memory_id or "").strip() or None,
            content_purged=True,
            memory=None,
        )
    if item.ledger_schema_version != LEDGER_SCHEMA_VERSION:
        return None
    return LedgerMirrorRow(
        memory_id=item.memory_id,
        item_revision=item.item_revision,
        status=item.status,
        source_state=item.source_state,
        canonical_memory_id=(item.canonical_memory_id or "").strip() or None,
        content_purged=False,
        memory=memory_item_to_memorydb(item),
    )


def _page_revision(fence: LedgerMirrorFence, rows: list[LedgerMirrorRow], aliases: list[LedgerMirrorAlias]) -> str:
    payload = {
        "epoch_id": fence.epoch_id,
        "rows": [
            {
                "memory_id": row.memory_id,
                "item_revision": row.item_revision,
                "status": row.status,
                "source_state": row.source_state,
                "canonical_memory_id": row.canonical_memory_id,
                "content_purged": row.content_purged,
                "memory": row.memory.model_dump(mode="json") if row.memory is not None else None,
            }
            for row in rows
        ],
        "aliases": [alias.__dict__ for alias in aliases],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _next_chain_revision(
    *,
    prior_chain_revision: str,
    page_revision: str,
    last_scanned_memory_id: str,
    scanned_page_count: int,
) -> str:
    payload = {
        "prior": prior_chain_revision,
        "page_revision": page_revision,
        "last_scanned_memory_id": last_scanned_memory_id,
        "scanned_page_count": scanned_page_count,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _failure(reason: str, *, fence: LedgerMirrorFence | None = None) -> LedgerMirrorPage:
    return LedgerMirrorPage(
        fence=fence,
        rows=(),
        aliases=(),
        page_revision="",
        chain_revision="",
        scanned_count=0,
        projected_count=0,
        next_cursor=None,
        final_page=False,
        failure_reason=reason,
    )


def read_authoritative_ledger_mirror_page(
    uid: str,
    *,
    cursor: str | None = None,
    page_size: int = DEFAULT_MIRROR_PAGE_SIZE,
    firestore_client: Any,
) -> LedgerMirrorPage:
    """Read one stable cursor-chain page; partial chains never carry authority."""

    if type(page_size) is not int or not 1 <= page_size <= MAX_MIRROR_PAGE_SIZE:
        return _failure("invalid_page_size")
    try:
        secret = cursor_secret()
        cursor_epoch, last_memory_id, prior_chain_revision, prior_scanned, prior_projected = _decode_cursor(
            cursor,
            uid=uid,
            secret=secret,
        )
    except (ValueError, UniversalListCursorError):
        return _failure("invalid_cursor")
    fence = _read_fence(uid, db_client=firestore_client)
    if fence is None:
        return _failure("migration_not_authoritative")
    if cursor_epoch is not None and cursor_epoch != fence.epoch_id:
        return _failure("epoch_changed", fence=fence)

    collection = firestore_client.collection(MemoryCollections(uid=uid).memory_items)
    query = collection.order_by("__name__", direction=firestore.Query.ASCENDING)
    if last_memory_id is not None:
        query = query.start_after({"__name__": collection.document(last_memory_id)})
    try:
        snapshots = list(query.limit(page_size + 1).stream())
    except Exception:
        return _failure("query_failed", fence=fence)
    has_more = len(snapshots) > page_size
    snapshots = snapshots[:page_size]
    rows: list[LedgerMirrorRow] = []
    aliases: list[LedgerMirrorAlias] = []
    try:
        for snapshot in snapshots:
            payload = snapshot.to_dict()
            if not isinstance(payload, dict):
                raise ValueError("malformed mirror row")
            item = MemoryItem.model_validate(payload)
            if item.uid != uid or item.memory_id != snapshot.id or item.account_generation != fence.account_generation:
                raise ValueError("mirror row identity mismatch")
            projected = _project_row(item)
            if projected is None:
                continue
            rows.append(projected)
            aliases.extend(_aliases(item))
    except Exception:
        return _failure("row_invalid", fence=fence)

    trailing_fence = _read_fence(uid, db_client=firestore_client)
    if trailing_fence != fence:
        return _failure("authority_changed", fence=fence)
    rows.sort(key=lambda row: row.memory_id)
    aliases.sort(key=lambda alias: (alias.alias_memory_id, alias.canonical_memory_id, alias.reason))
    revision = _page_revision(fence, rows, aliases)
    last_scanned_memory_id = snapshots[-1].id if snapshots else (last_memory_id or "")
    chain_revision = _next_chain_revision(
        prior_chain_revision=prior_chain_revision,
        page_revision=revision,
        last_scanned_memory_id=last_scanned_memory_id,
        scanned_page_count=len(snapshots),
    )
    scanned_count = prior_scanned + len(snapshots)
    projected_count = prior_projected + len(rows)
    next_cursor = None
    if has_more and snapshots:
        next_cursor = _encode_cursor(
            uid=uid,
            epoch_id=fence.epoch_id,
            last_memory_id=snapshots[-1].id,
            chain_revision=chain_revision,
            scanned_count=scanned_count,
            projected_count=projected_count,
            secret=secret,
        )
    return LedgerMirrorPage(
        fence=fence,
        rows=tuple(rows),
        aliases=tuple(aliases),
        page_revision=revision,
        chain_revision=chain_revision,
        scanned_count=scanned_count,
        projected_count=projected_count,
        next_cursor=next_cursor,
        final_page=not has_more,
    )


__all__ = [
    "DEFAULT_MIRROR_PAGE_SIZE",
    "LedgerMirrorAlias",
    "LedgerMirrorFence",
    "LedgerMirrorPage",
    "LedgerMirrorRow",
    "MAX_MIRROR_PAGE_SIZE",
    "MIRROR_SCHEMA_VERSION",
    "read_authoritative_ledger_mirror_page",
]
