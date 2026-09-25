"""Independent, bounded scheduler path for knowledge-ledger account cutover.

This module deliberately has no dependency on short-term maintenance.  It
inventories canonical apply-control documents with its own durable cursor, then
re-authorizes and drains a bounded account page. A slow maintenance run
therefore cannot prevent ledger migration from making progress.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, cast

from google.cloud import firestore

from database._client import get_firestore_client
from database.memory_collections import MemoryCollections
from models.memory_apply import WriterMode
from utils.executors import db_executor, run_blocking
from utils.jit_rollout import JITDecisionStage, resolve_jit_rollout
from utils.memory.knowledge_ledger_migration import (
    publish_ledger_migration_cutover,
    run_ledger_migration_sweep,
)

logger = logging.getLogger(__name__)

MAX_LEDGER_DRAIN_UIDS_PER_RUN = 20
MAX_LEDGER_DRAIN_ERRORS = 16
LEDGER_ROW_AUTHORIZATION_TIMEOUT_SECONDS = 15.0
LEDGER_DRAIN_CURSOR_PATH = "knowledge_ledger_migration_control/inventory_cursor"
LEDGER_DRAIN_CURSOR_SCHEMA_VERSION = 1
LEDGER_TRANSITION_OWNER = "knowledge-ledger-migration.v1"
LEDGER_DRAIN_ENABLED_ENV = "KNOWLEDGE_LEDGER_DRAIN_ENABLED"
LEDGER_DRAIN_UID_ALLOWLIST_ENV = "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST"


class LedgerDrainInventoryUnavailable(RuntimeError):
    """The bounded migration inventory or its progress cursor is unavailable."""


def ledger_drain_enabled_from_environment() -> bool:
    """Return the explicit operational gate for the scheduled drain job."""

    return (os.getenv(LEDGER_DRAIN_ENABLED_ENV) or "").strip().lower() in {"1", "true", "on", "yes"}


def ledger_drain_uid_allowlist_from_environment() -> frozenset[str]:
    """Parse the optional job-scoped UID fence without exposing its contents in logs."""

    raw = os.getenv(LEDGER_DRAIN_UID_ALLOWLIST_ENV) or ""
    values = frozenset(part.strip() for part in raw.split(",") if part.strip())
    if any("/" in uid or any(character.isspace() for character in uid) for uid in values):
        raise ValueError(f"{LEDGER_DRAIN_UID_ALLOWLIST_ENV} contains an invalid UID")
    return values


@dataclass(frozen=True)
class LedgerDrainInventoryPage:
    uids: tuple[str, ...]
    last_path: str
    cursor_generation: int
    scanned_documents: int


@dataclass
class LedgerDrainSummary:
    inventoried_users: int = 0
    scanned_documents: int = 0
    attempted_users: int = 0
    allowlist_blocked_users: int = 0
    rollout_blocked_users: int = 0
    authorization_revoked_users: int = 0
    remaining_users: int = 0
    cutover_users: int = 0
    migrated_rows: int = 0
    errors: list[str] = field(default_factory=list)


def _read_cursor(db_client: Any) -> tuple[str, int]:
    try:
        snapshot = db_client.document(LEDGER_DRAIN_CURSOR_PATH).get()
    except Exception as exc:
        raise LedgerDrainInventoryUnavailable("ledger drain cursor unavailable") from exc
    if not getattr(snapshot, "exists", False):
        return "", 0
    payload = snapshot.to_dict()
    if not isinstance(payload, dict) or payload.get("schema_version") != LEDGER_DRAIN_CURSOR_SCHEMA_VERSION:
        raise LedgerDrainInventoryUnavailable("ledger drain cursor malformed")
    last_path = payload.get("last_path", "")
    generation = payload.get("generation", 0)
    if not isinstance(last_path, str) or not isinstance(generation, int) or generation < 0:
        raise LedgerDrainInventoryUnavailable("ledger drain cursor malformed")
    return last_path, generation


def _write_cursor(db_client: Any, page: LedgerDrainInventoryPage) -> None:
    if not page.last_path:
        return
    ref = db_client.document(LEDGER_DRAIN_CURSOR_PATH)
    payload = {
        "schema_version": LEDGER_DRAIN_CURSOR_SCHEMA_VERSION,
        "last_path": page.last_path,
        "generation": page.cursor_generation + 1,
    }
    try:
        transaction_factory = getattr(db_client, "transaction", None)
        if callable(transaction_factory):
            transaction = transaction_factory()

            def write_transaction(tx: Any) -> None:
                snapshot = ref.get(transaction=tx)
                live = snapshot.to_dict() if getattr(snapshot, "exists", False) else {}
                live_generation = live.get("generation", 0) if isinstance(live, dict) else 0
                if live_generation != page.cursor_generation:
                    raise LedgerDrainInventoryUnavailable("ledger drain cursor generation conflict")
                tx.set(ref, payload, merge=True)

            cast(Any, firestore.transactional(write_transaction))(transaction)
            return
        current = ref.get()
        current_payload = current.to_dict() if getattr(current, "exists", False) else {}
        current_generation = current_payload.get("generation", 0) if isinstance(current_payload, dict) else 0
        if current_generation != page.cursor_generation:
            raise LedgerDrainInventoryUnavailable("ledger drain cursor generation conflict")
        ref.set(payload, merge=True)
    except LedgerDrainInventoryUnavailable:
        raise
    except Exception as exc:
        raise LedgerDrainInventoryUnavailable("ledger drain cursor unavailable") from exc


def _inventory_page_from_snapshots(
    snapshots: list[Any],
    *,
    last_path: str,
    cursor_generation: int,
    track_cursor: bool = True,
) -> LedgerDrainInventoryPage:
    uids: list[str] = []
    for snapshot in snapshots:
        path = str(getattr(getattr(snapshot, "reference", None), "path", ""))
        if not path:
            raise LedgerDrainInventoryUnavailable("ledger drain inventory row has no document path")
        if track_cursor:
            last_path = path
        parts = path.split("/")
        if len(parts) != 4 or parts[0] != "users" or parts[2:] != ["memory_state", "apply_control"]:
            continue
        payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
        uid = payload.get("uid") if isinstance(payload, dict) else None
        writer_mode = payload.get("writer_mode", WriterMode.compatibility.value) if isinstance(payload, dict) else None
        if not isinstance(uid, str) or uid != parts[1] or not uid.strip() or "/" in uid:
            raise LedgerDrainInventoryUnavailable("ledger drain apply-control row malformed")
        try:
            mode = WriterMode(writer_mode)
        except (TypeError, ValueError) as exc:
            raise LedgerDrainInventoryUnavailable("ledger drain apply-control row malformed") from exc
        if mode is WriterMode.ledger:
            continue
        if mode is WriterMode.transitioning_to_ledger:
            owner = cast(dict[str, Any], payload).get("writer_transition_owner")
            if owner != LEDGER_TRANSITION_OWNER:
                continue
        if uid not in uids:
            uids.append(uid)
    return LedgerDrainInventoryPage(
        uids=tuple(uids),
        last_path=last_path,
        cursor_generation=cursor_generation,
        scanned_documents=len(snapshots),
    )


def _bounded_allowlist_inventory(db_client: Any, uid_allowlist: Collection[object]) -> LedgerDrainInventoryPage:
    """Read only the explicitly scoped accounts, without touching the fair global cursor."""

    raw_uids = tuple(uid_allowlist)
    string_uids = tuple(uid for uid in raw_uids if isinstance(uid, str))
    if len(string_uids) != len(raw_uids):
        raise LedgerDrainInventoryUnavailable("ledger drain UID allowlist is malformed")
    uids = tuple(sorted({uid.strip() for uid in string_uids}))
    if not uids:
        return LedgerDrainInventoryPage(uids=(), last_path="", cursor_generation=0, scanned_documents=0)
    if len(uids) > MAX_LEDGER_DRAIN_UIDS_PER_RUN:
        raise LedgerDrainInventoryUnavailable("ledger drain UID allowlist exceeds the bounded page limit")
    snapshots: list[Any] = []
    try:
        for uid in uids:
            if not uid or "/" in uid or any(character.isspace() for character in uid):
                raise LedgerDrainInventoryUnavailable("ledger drain UID allowlist is malformed")
            snapshot = db_client.document(MemoryCollections(uid=uid).memory_apply_control_state).get()
            if getattr(snapshot, "exists", False):
                snapshots.append(snapshot)
    except LedgerDrainInventoryUnavailable:
        raise
    except Exception as exc:
        raise LedgerDrainInventoryUnavailable("ledger drain allowlist inventory unavailable") from exc
    return _inventory_page_from_snapshots(snapshots, last_path="", cursor_generation=0, track_cursor=False)


def bounded_ledger_drain_inventory(
    db_client: Any,
    *,
    limit: int = MAX_LEDGER_DRAIN_UIDS_PER_RUN,
    uid_allowlist: Collection[str] | None = None,
) -> LedgerDrainInventoryPage:
    """Read one fair, bounded page of canonical apply-control documents."""

    bounded_limit = max(1, min(MAX_LEDGER_DRAIN_UIDS_PER_RUN, int(limit)))
    if uid_allowlist is not None:
        return _bounded_allowlist_inventory(db_client, uid_allowlist)
    collection_group = getattr(db_client, "collection_group", None)
    if not callable(collection_group):
        raise LedgerDrainInventoryUnavailable("ledger drain apply-control inventory unavailable")
    cursor_path, cursor_generation = _read_cursor(db_client)
    cursor_snapshot = None
    if cursor_path:
        try:
            candidate = db_client.document(cursor_path).get()
        except Exception as exc:
            raise LedgerDrainInventoryUnavailable("ledger drain cursor snapshot unavailable") from exc
        if getattr(candidate, "exists", False):
            cursor_snapshot = candidate
    try:
        query: Any = cast(Any, collection_group("memory_state")).order_by("__name__")
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        snapshots = list(query.limit(bounded_limit).stream())
        if not snapshots and cursor_snapshot is not None:
            snapshots = list(
                cast(Any, collection_group("memory_state")).order_by("__name__").limit(bounded_limit).stream()
            )

        return _inventory_page_from_snapshots(
            snapshots,
            last_path=cursor_path,
            cursor_generation=cursor_generation,
        )
    except LedgerDrainInventoryUnavailable:
        raise
    except Exception as exc:
        raise LedgerDrainInventoryUnavailable("ledger drain apply-control inventory unavailable") from exc


def commit_ledger_drain_inventory(db_client: Any, page: LedgerDrainInventoryPage) -> None:
    """Advance only after the complete bounded page has returned to the caller."""

    _write_cursor(db_client, page)


def _append_error(summary: LedgerDrainSummary, uid: str, operation: str, exc: Exception) -> None:
    if len(summary.errors) < MAX_LEDGER_DRAIN_ERRORS:
        summary.errors.append(f"uid={uid}:{operation}:{type(exc).__name__}")


async def run_knowledge_ledger_drain(
    *,
    db_client: Any = None,
    now: datetime | None = None,
    inventory_limit: int = MAX_LEDGER_DRAIN_UIDS_PER_RUN,
    inventory_provider: Callable[..., Any] = bounded_ledger_drain_inventory,
    uid_allowlist: Collection[str] | None = None,
) -> LedgerDrainSummary:
    """Drain and publish one independently inventoried migration page."""

    # Resolved per call rather than bound at import, and dispatched off the event loop:
    # building the Firestore client is blocking work like every other db call below.
    client = db_client if db_client is not None else await run_blocking(db_executor, get_firestore_client)
    inventory_kwargs: dict[str, Any] = {"limit": inventory_limit}
    if uid_allowlist is not None:
        inventory_kwargs["uid_allowlist"] = uid_allowlist
    page = await run_blocking(db_executor, inventory_provider, client, **inventory_kwargs)
    if not isinstance(page, LedgerDrainInventoryPage):
        raise LedgerDrainInventoryUnavailable("ledger drain inventory page malformed")
    summary = LedgerDrainSummary(
        inventoried_users=len(page.uids),
        scanned_documents=page.scanned_documents,
    )
    completed_at = now or datetime.now(timezone.utc)
    authority_loop = asyncio.get_running_loop()

    def fresh_rollout_authorizer(uid: str) -> Callable[..., bool]:
        def authorize(*_context: str) -> bool:
            future = asyncio.run_coroutine_threadsafe(
                resolve_jit_rollout(uid, stage=JITDecisionStage.INGRESS, force_refresh=True),
                authority_loop,
            )
            try:
                return future.result(timeout=LEDGER_ROW_AUTHORIZATION_TIMEOUT_SECONDS).permits_work
            except Exception as exc:
                future.cancel()
                logger.warning("knowledge_ledger_drain: uid=%s authorization_failed=%s", uid, type(exc).__name__)
                return False

        return authorize

    for uid in page.uids:
        if uid_allowlist is not None and uid not in uid_allowlist:
            summary.allowlist_blocked_users += 1
            continue
        try:
            decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.INGRESS, force_refresh=True)
        except Exception as exc:
            _append_error(summary, uid, "rollout", exc)
            continue
        if not decision.permits_work:
            summary.rollout_blocked_users += 1
            continue
        summary.attempted_users += 1
        authorizer = fresh_rollout_authorizer(uid)
        try:
            result = await run_blocking(
                db_executor,
                run_ledger_migration_sweep,
                uid,
                db_client=client,
                completed_at=completed_at,
                publish=False,
                mutation_authorizer=authorizer,
                publication_authorizer=authorizer,
            )
        except Exception as exc:
            _append_error(summary, uid, "migration", exc)
            continue
        summary.migrated_rows += result.migrated_long_term_count
        if getattr(result, "authorization_revoked", False):
            summary.authorization_revoked_users += 1
            continue
        if result.remaining_live_legacy_count:
            summary.remaining_users += 1
            continue
        try:
            await run_blocking(
                db_executor,
                publish_ledger_migration_cutover,
                uid,
                db_client=client,
                publication_authorizer=authorizer,
                mutation_authorizer=authorizer,
                migrated_long_term_count=result.migrated_long_term_count,
                adjudicated_short_term_count=result.adjudicated_short_term_count,
                completed_at=completed_at,
            )
        except Exception as exc:
            _append_error(summary, uid, "publication", exc)
            continue
        summary.cutover_users += 1

    if not summary.errors:
        await run_blocking(db_executor, commit_ledger_drain_inventory, client, page)
    logger.info(
        "knowledge_ledger_drain: scanned=%d inventoried=%d attempted=%d allowlist_blocked=%d blocked=%d revoked=%d "
        "remaining=%d cutover=%d migrated_rows=%d errors=%d",
        summary.scanned_documents,
        summary.inventoried_users,
        summary.attempted_users,
        summary.allowlist_blocked_users,
        summary.rollout_blocked_users,
        summary.authorization_revoked_users,
        summary.remaining_users,
        summary.cutover_users,
        summary.migrated_rows,
        len(summary.errors),
    )
    return summary


__all__ = [
    "LEDGER_DRAIN_CURSOR_PATH",
    "LEDGER_DRAIN_ENABLED_ENV",
    "LEDGER_DRAIN_UID_ALLOWLIST_ENV",
    "LedgerDrainInventoryPage",
    "LedgerDrainInventoryUnavailable",
    "LedgerDrainSummary",
    "MAX_LEDGER_DRAIN_UIDS_PER_RUN",
    "bounded_ledger_drain_inventory",
    "commit_ledger_drain_inventory",
    "ledger_drain_enabled_from_environment",
    "ledger_drain_uid_allowlist_from_environment",
    "run_knowledge_ledger_drain",
]
