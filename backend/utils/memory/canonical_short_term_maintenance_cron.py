"""Scheduled universal short-term maintenance (TTL audit, owed explicit intake and outbox delivery).

Hosted by the dedicated ``memory-maintenance-job`` Cloud Run Job
(``backend/modal/memory_maintenance_job.py``). The global maintenance switch
remains explicit. User selection comes only from a bounded injectable
inventory; this module never scans all users or consults a UID allowlist.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any, Iterable, Optional, Protocol, cast

from pydantic import ValidationError
from google.cloud import firestore

from database._client import db as default_db_client
from jobs.short_term_lifecycle_worker import fetch_expiry_urgent_short_term_memory_items_firestore
from models.product_memory import DEFAULT_SHORT_TERM_TTL
from utils.executors import db_executor, run_blocking
from utils.log_sanitizer import sanitize_validation_error
from utils.memory.canonical_required_processing import invoke_required_memory_processor
from utils.memory.short_term_promotion import (
    CanonicalShortTermMaintenanceReport,
    run_canonical_short_term_maintenance_async,
)
from utils.memory.memory_system import (
    CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH,
    CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION,
    CANONICAL_MEMORY_MAINTENANCE_REGISTRY_SCHEMA_VERSION,
)
from utils.memory.promotion_flex import (
    MEMORY_PROMOTION_FLEX_LEASE_SECONDS,
    PromotionFlexDeferred,
    PromotionFlexRunRouter,
)

logger = logging.getLogger(__name__)

MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV = "MEMORY_CANONICAL_MAINTENANCE_ENABLED"
MAX_MAINTENANCE_UIDS_PER_RUN = 400
EXPIRY_ADJUDICATION_LOOKAHEAD = DEFAULT_SHORT_TERM_TTL / 2
CANONICAL_MEMORY_MAINTENANCE_SEED_CURSOR_PATH = "canonical_memory_maintenance_control/seed_cursor"
CANONICAL_MEMORY_MAINTENANCE_SEED_SCHEMA_VERSION = 1


class CanonicalMaintenanceInventoryUnavailable(RuntimeError):
    """The deployment did not provide a bounded UID inventory seam."""


class CanonicalMaintenanceUIDInventory(Protocol):
    def __call__(self, db_client: Any, limit: int) -> Iterable[str]: ...


@dataclass(frozen=True)
class ExpiryOrderedMaintenanceInventory:
    uids: tuple[str, ...]
    candidate_item_count: int = 0
    expired_active_item_count: int = 0


def expiry_ordered_maintenance_uid_inventory(
    db_client: Any,
    *,
    now: datetime,
    limit: int = MAX_MAINTENANCE_UIDS_PER_RUN,
) -> ExpiryOrderedMaintenanceInventory:
    """Return UIDs ordered by their earliest approaching Short-term expiry."""
    bounded_limit = max(1, min(MAX_MAINTENANCE_UIDS_PER_RUN, int(limit)))
    deadline = now.astimezone(timezone.utc) + EXPIRY_ADJUDICATION_LOOKAHEAD
    try:
        items = fetch_expiry_urgent_short_term_memory_items_firestore(
            db_client=db_client,
            deadline=deadline,
        )
    except Exception as exc:
        raise CanonicalMaintenanceInventoryUnavailable("expiry-ordered canonical memory inventory failed") from exc

    uids: list[str] = []
    expired_active_items = 0
    for item in items:
        if item.effective_expiry <= now:
            expired_active_items += 1
        if item.uid not in uids:
            uids.append(item.uid)
        if len(uids) >= bounded_limit:
            break
    return ExpiryOrderedMaintenanceInventory(
        uids=tuple(uids),
        candidate_item_count=len(items),
        expired_active_item_count=expired_active_items,
    )


def _registry_uid(snapshot: Any) -> Optional[str]:
    payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
    if not isinstance(payload, dict):
        return None
    uid = payload.get("uid")
    schema_version = payload.get("schema_version")
    if (
        not isinstance(uid, str)
        or not uid.strip()
        or schema_version != CANONICAL_MEMORY_MAINTENANCE_REGISTRY_SCHEMA_VERSION
    ):
        raise CanonicalMaintenanceInventoryUnavailable("canonical UID registry entry is malformed")
    return uid.strip()


def _read_registry_cursor_state(db_client: Any) -> tuple[str, int]:
    ref = db_client.document(CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH)
    try:
        snapshot = ref.get()
    except Exception as exc:
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor unavailable") from exc
    if not getattr(snapshot, "exists", False):
        # Reads must stay side-effect free. The first durable cursor write is
        # performed by the generation-fenced commit below; creating an empty
        # document here would make ``persist_cursor=False`` mutate state.
        return "", 0
    payload = snapshot.to_dict()
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor is malformed")
    last_uid = payload.get("last_uid", "")
    generation = payload.get("generation", 0)
    if not isinstance(last_uid, str) or not isinstance(generation, int) or generation < 0:
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor is malformed")
    return last_uid, generation


def _persist_registry_cursor(db_client: Any, last_uid: str, *, expected_generation: int | None = None) -> None:
    payload = {"schema_version": 1, "last_uid": last_uid}
    try:
        ref = db_client.document(CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH)
        current = ref.get()
        current_payload = current.to_dict() if getattr(current, "exists", False) else {}
        current_generation = current_payload.get("generation", 0) if isinstance(current_payload, dict) else 0
        if not isinstance(current_generation, int) or current_generation < 0:
            raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor is malformed")
        if expected_generation is not None and current_generation != expected_generation:
            raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor generation conflict")
        next_payload = {**payload, "generation": current_generation + 1}
        transaction_factory = getattr(db_client, "transaction", None)
        if callable(transaction_factory):
            try:
                transaction = transaction_factory()

                def write_transaction(tx: Any) -> None:
                    live_snapshot = ref.get(transaction=tx)
                    live_payload = live_snapshot.to_dict() if getattr(live_snapshot, "exists", False) else {}
                    live_generation = live_payload.get("generation", 0) if isinstance(live_payload, dict) else 0
                    if expected_generation is not None and live_generation != expected_generation:
                        raise CanonicalMaintenanceInventoryUnavailable(
                            "canonical maintenance cursor generation conflict"
                        )
                    tx.set(ref, next_payload, merge=True)

                cast(Any, firestore.transactional(write_transaction))(transaction)
                return
            except TypeError:
                pass
        ref.set(next_payload, merge=True)
    except Exception as exc:
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor unavailable") from exc


def _read_seed_cursor(db_client: Any) -> str:
    ref = db_client.document(CANONICAL_MEMORY_MAINTENANCE_SEED_CURSOR_PATH)
    try:
        snapshot = ref.get()
    except Exception as exc:
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance seed cursor unavailable") from exc
    if not getattr(snapshot, "exists", False):
        return ""
    payload = snapshot.to_dict()
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != CANONICAL_MEMORY_MAINTENANCE_SEED_SCHEMA_VERSION
    ):
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance seed cursor is malformed")
    last_path = payload.get("last_path", "")
    if not isinstance(last_path, str):
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance seed cursor is malformed")
    return last_path


def _persist_seed_cursor(db_client: Any, last_path: str) -> None:
    payload = {
        "schema_version": CANONICAL_MEMORY_MAINTENANCE_SEED_SCHEMA_VERSION,
        "last_path": last_path,
    }
    try:
        db_client.document(CANONICAL_MEMORY_MAINTENANCE_SEED_CURSOR_PATH).set(payload, merge=True)
    except Exception as exc:
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance seed cursor unavailable") from exc


def _seed_registry_from_existing_memory_states(db_client: Any, *, limit: int) -> None:
    """Discover pre-registry canonical accounts through a bounded resumable scan.

    Earlier canonical accounts may already have ``memory_state/apply_control``
    but no neutral maintenance marker because the registry was introduced later.
    A separate document-path cursor lets this one-time discovery progress across
    invocations without turning maintenance into an unbounded user scan. Fakes
    and deployments without collection-group support retain the explicit
    registry-only seam and simply skip this optional seed pass.
    """
    collection_group_factory = getattr(db_client, "collection_group", None)
    if not callable(collection_group_factory):
        return
    collection_group = cast(Callable[[str], Any], collection_group_factory)
    bounded_limit = max(1, min(MAX_MAINTENANCE_UIDS_PER_RUN, int(limit)))
    cursor_path = _read_seed_cursor(db_client)
    cursor_snapshot = None
    if cursor_path:
        try:
            candidate = db_client.document(cursor_path).get()
        except Exception as exc:
            raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance seed cursor unavailable") from exc
        if getattr(candidate, "exists", False):
            cursor_snapshot = candidate
    try:
        query = collection_group("memory_state").order_by("__name__")
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        page = list(query.limit(bounded_limit).stream())
        if not page and cursor_snapshot is not None:
            # Rotate after reaching the tail so every existing account is
            # revisited when new state documents appear later.
            page = list(collection_group("memory_state").order_by("__name__").limit(bounded_limit).stream())
        last_path = cursor_path
        for snapshot in page:
            path = getattr(getattr(snapshot, "reference", None), "path", "")
            parts = path.split("/") if isinstance(path, str) else []
            if len(parts) != 4 or parts[0] != "users" or parts[2] != "memory_state" or parts[3] != "apply_control":
                last_path = path if isinstance(path, str) else last_path
                continue
            payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
            uid = parts[1]
            if not isinstance(payload, dict) or payload.get("uid") != uid or not uid.strip() or "/" in uid:
                raise CanonicalMaintenanceInventoryUnavailable("canonical memory apply state is malformed")
            registry_ref = db_client.document(f"{CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION}/{uid}")
            registry_ref.set(
                {
                    "uid": uid,
                    "schema_version": CANONICAL_MEMORY_MAINTENANCE_REGISTRY_SCHEMA_VERSION,
                }
            )
            last_path = path
        if page:
            _persist_seed_cursor(db_client, last_path)
    except CanonicalMaintenanceInventoryUnavailable:
        raise
    except Exception as exc:
        raise CanonicalMaintenanceInventoryUnavailable("canonical memory state registry seed failed") from exc


def bounded_canonical_memory_uid_inventory(
    db_client: Any,
    *,
    limit: int = MAX_MAINTENANCE_UIDS_PER_RUN,
    persist_cursor: bool = True,
) -> tuple[str, ...]:
    """Derive a deterministic, bounded UID page from the neutral registry.

    A persisted UID cursor makes successive runs progress through the complete
    registry. Once the end is reached the query wraps to the beginning, while
    keeping each registry read bounded by ``limit``. The maintenance cron can
    defer cursor persistence until a UID actually finishes so a Flex budget
    stop cannot skip later accounts.
    """
    bounded_limit = max(1, min(MAX_MAINTENANCE_UIDS_PER_RUN, int(limit)))
    collection = getattr(db_client, "collection", None)
    if not callable(collection):
        raise CanonicalMaintenanceInventoryUnavailable(
            "bounded canonical UID registry is unavailable; provide a registry/index or injectable inventory"
        )
    _seed_registry_from_existing_memory_states(db_client, limit=bounded_limit)
    cursor, cursor_generation = _read_registry_cursor_state(db_client)
    try:
        # Firestore's public query objects and the strict test fakes both expose
        # this fluent surface, but the callable narrowing above intentionally
        # leaves the return type opaque.  Keep that injection seam while making
        # the structural expectation explicit to the type checker.
        registry = cast(Any, collection(CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION))
        query = registry.where("uid", ">", cursor) if cursor else registry
        query = query.order_by("uid")
        page = list(query.limit(bounded_limit).stream())
        if cursor and len(page) < bounded_limit:
            wrapped = list(registry.order_by("uid").limit(bounded_limit - len(page)).stream())
            page.extend(wrapped)
        uids: list[str] = []
        for snapshot in page:
            uid = _registry_uid(snapshot)
            if uid and uid not in uids:
                uids.append(uid)
        if persist_cursor and uids:
            _persist_registry_cursor(db_client, uids[-1], expected_generation=cursor_generation)
        return tuple(uids[:bounded_limit])
    except CanonicalMaintenanceInventoryUnavailable:
        raise
    except Exception as exc:
        raise CanonicalMaintenanceInventoryUnavailable("bounded canonical UID registry query failed") from exc


def _resolve_maintenance_uids(
    db_client: Any,
    *,
    uid_inventory: Optional[CanonicalMaintenanceUIDInventory],
    limit: int = MAX_MAINTENANCE_UIDS_PER_RUN,
) -> tuple[str, ...]:
    if uid_inventory is None:
        return bounded_canonical_memory_uid_inventory(db_client, limit=limit)
    try:
        values = uid_inventory(db_client, max(1, min(MAX_MAINTENANCE_UIDS_PER_RUN, int(limit))))
    except TypeError:
        # Keep the seam easy to inject in small tests and operator wrappers.
        values = cast(Any, uid_inventory)(db_client)
    normalized = sorted({uid.strip() for uid in values if isinstance(uid, str) and uid.strip()})
    return tuple(normalized[: max(1, min(MAX_MAINTENANCE_UIDS_PER_RUN, int(limit)))])


def _empty_errors() -> list[str]:
    return []


def canonical_maintenance_enabled() -> bool:
    """Whether *this process* hosts the ST→LT cron.

    Not a product rollout flag — that is ``MEMORY_ENABLED``, which is universal for
    authenticated accounts. This one is per-deployable routing, so the ``"false"``
    default is correct: only ``memory-maintenance-job`` sets it true, and
    ``scripts/runtime_env_validation/manifest.py`` fails the build if any other job
    or request-path surface does. Read the deployed value from
    ``deploy/runtime_env/*.overlay.yaml``, not from this default.
    """
    raw = os.getenv(MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "false")
    return raw.lower() == "true"


@dataclass
class CanonicalShortTermMaintenanceCronSummary:
    run_id: str
    user_count: int = 0
    inventory_source: str = "bounded_registry"
    inventory_complete: bool = False
    expiry_urgent_users: int = 0
    expiry_urgent_items: int = 0
    expired_active_candidates_total: int = 0
    expired_without_terminal_disposition_total: int = 0
    expired_with_recorded_disposition_total: int = 0
    expired_terminal_dispositions_total: int = 0
    routed_total: int = 0
    promoted_total: int = 0
    skipped_users: int = 0
    maintained_users: int = 0
    recurrence_receipts_delivered: int = 0
    flex_deferred: bool = False
    outbox_delivered_total: int = 0
    outbox_retryable_failures_total: int = 0
    outbox_dead_letters_total: int = 0
    outbox_ack_failures_total: int = 0
    completed_uids: tuple[str, ...] = ()
    errors: list[str] = field(default_factory=_empty_errors)


def _coerce_run_id(run_id: Optional[str], *, now: datetime) -> str:
    if run_id:
        return run_id
    return f'cron-{now.strftime("%Y%m%d%H%M%S")}'


def _skipped_reason(report: CanonicalShortTermMaintenanceReport) -> Optional[str]:
    if report.skipped_reason:
        return report.skipped_reason
    return None


def _promoted_count(report: CanonicalShortTermMaintenanceReport) -> int:
    return report.promoted_count


def _safe_maintenance_error(uid: str, exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return f"uid={uid}: ValidationError: {sanitize_validation_error(cast(Any, exc))}"
    return f"uid={uid}: {type(exc).__name__}"


async def run_canonical_short_term_maintenance_cron(
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
    recurrence_inbox_drain: Optional[Callable[..., int]] = None,
    uid_inventory: Optional[CanonicalMaintenanceUIDInventory] = None,
    inventory_limit: int = MAX_MAINTENANCE_UIDS_PER_RUN,
) -> CanonicalShortTermMaintenanceCronSummary:
    """Run maintenance for one bounded UID inventory page.

    Cloud Scheduler owns cadence and global enablement. The inventory is an
    explicit seam because safe all-user enumeration requires an indexed registry
    outside this maintenance job. Missing inventory fails closed and reports the
    operational dependency; it never silently runs a code UID list.
    """
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    maintenance_now = current_time if now is not None else None
    effective_run_id = _coerce_run_id(run_id, now=current_time)
    if not canonical_maintenance_enabled():
        logger.info(
            "canonical_short_term_maintenance_cron: disabled run_id=%s",
            effective_run_id,
        )
        return CanonicalShortTermMaintenanceCronSummary(run_id=effective_run_id, user_count=0)

    client = db_client if db_client is not None else default_db_client
    flex_run = await run_blocking(db_executor, PromotionFlexRunRouter, db_client=client, force_enabled=True)
    expiry_inventory = ExpiryOrderedMaintenanceInventory(uids=())
    registry_uids: tuple[str, ...] = ()
    registry_cursor_generation = 0
    inventory_errors: list[str] = []
    if uid_inventory is None:
        try:
            expiry_inventory = await run_blocking(
                db_executor,
                expiry_ordered_maintenance_uid_inventory,
                client,
                now=current_time,
                limit=inventory_limit,
            )
        except CanonicalMaintenanceInventoryUnavailable as exc:
            inventory_errors.append("canonical_expiry_inventory_unavailable")
            logger.warning(
                "canonical_short_term_maintenance_cron: canonical_expiry_inventory_unavailable (%s)",
                type(exc).__name__,
            )
        try:
            # Keep compatibility with the injected expiry-only backstop,
            # which intentionally uses a sentinel client without Firestore.
            # Real clients expose ``document`` and therefore receive the
            # generation snapshot used by the final CAS commit.
            if callable(getattr(client, "document", None)):
                _registry_cursor, registry_cursor_generation = await run_blocking(
                    db_executor, _read_registry_cursor_state, client
                )
            registry_uids = await run_blocking(
                db_executor,
                bounded_canonical_memory_uid_inventory,
                client,
                limit=inventory_limit,
                persist_cursor=False,
            )
        except CanonicalMaintenanceInventoryUnavailable as exc:
            inventory_errors.append("canonical_uid_inventory_unavailable")
            logger.warning(
                "canonical_short_term_maintenance_cron: canonical_uid_inventory_unavailable (%s)",
                type(exc).__name__,
            )
        uids = tuple(dict.fromkeys((*expiry_inventory.uids, *registry_uids)))[
            : max(1, min(MAX_MAINTENANCE_UIDS_PER_RUN, int(inventory_limit)))
        ]
    else:
        try:
            uids = await run_blocking(
                db_executor, _resolve_maintenance_uids, client, uid_inventory=uid_inventory, limit=inventory_limit
            )
        except CanonicalMaintenanceInventoryUnavailable as exc:
            inventory_errors.append("canonical_uid_inventory_unavailable")
            logger.warning(
                "canonical_short_term_maintenance_cron: canonical_uid_inventory_unavailable (%s)",
                type(exc).__name__,
            )
            uids = ()

    if not uids and inventory_errors:
        message = "canonical_uid_inventory_unavailable"
        return CanonicalShortTermMaintenanceCronSummary(
            run_id=effective_run_id,
            inventory_source="unavailable",
            inventory_complete=False,
            errors=[message],
        )
    summary = CanonicalShortTermMaintenanceCronSummary(
        run_id=effective_run_id,
        user_count=len(uids),
        inventory_source=(
            "injected"
            if uid_inventory is not None
            else (
                "expiry_ordered+bounded_registry"
                if expiry_inventory.uids and registry_uids
                else "expiry_ordered" if expiry_inventory.uids else "bounded_registry"
            )
        ),
        inventory_complete=not inventory_errors,
        expiry_urgent_users=len(expiry_inventory.uids),
        expiry_urgent_items=expiry_inventory.candidate_item_count,
        expired_active_candidates_total=expiry_inventory.expired_active_item_count,
        errors=inventory_errors,
    )
    logger.info(
        "canonical_short_term_maintenance_cron: start run_id=%s user_count=%d flex=%s",
        effective_run_id,
        len(uids),
        flex_run.control.enabled,
    )
    completed_uids: set[str] = set()
    for uid in uids:
        if flex_run.control.enabled and not flex_run.job_budget_fits():
            summary.flex_deferred = True
            logger.info(
                "canonical_short_term_maintenance_cron: uid=%s flex_deferred=job_budget",
                uid,
            )
            break
        # Owed explicit normalization and ordinary intake share the bounded Flex
        # router. Retrospective semantic cleanup remains Dream's responsibility.
        model = flex_run.llm_for_uid(
            uid,
            standard_feature="memory_l2",
            flex_feature="memory_l2_flex",
            workload="required_memory_intake",
        )
        if model is None:
            summary.errors.append(f"uid={uid}: required_processor_not_configured")

        def normalize(item):
            return invoke_required_memory_processor(item, model)

        def decide_observations(items):
            from utils.memory.canonical_consolidation import plan_observation_intake

            if model is None:
                raise RuntimeError('observation_intake_model_unavailable')
            result = plan_observation_intake(items, llm=model)
            flex_run.assert_result_current()
            return result

        try:
            report = await run_canonical_short_term_maintenance_async(
                uid,
                db_client=client,
                now=maintenance_now,
                run_id=effective_run_id,
                required_processor=normalize if model is not None else None,
                observation_planner=decide_observations,
                required_processing_limit=25 if model is not None else 0,
                required_processing_attempt_lease_seconds=MEMORY_PROMOTION_FLEX_LEASE_SECONDS,
                required_processing_result_guard=flex_run.assert_result_current,
                job_budget_guard=flex_run.require_job_budget,
            )
        except PromotionFlexDeferred as exc:
            summary.flex_deferred = True
            logger.info(
                "canonical_short_term_maintenance_cron: uid=%s flex_deferred=%s",
                uid,
                type(exc).__name__,
            )
            break
        except Exception as exc:
            message = _safe_maintenance_error(uid, exc)
            summary.errors.append(message)
            logger.warning("canonical_short_term_maintenance_cron: failed %s", message)
            completed_uids.add(uid)
            continue

        promoted = _promoted_count(report)
        skipped = _skipped_reason(report)
        summary.routed_total += report.routed_count
        summary.promoted_total += promoted
        if report.lifecycle is not None:
            summary.expired_without_terminal_disposition_total += report.lifecycle.lifecycle_created_count
            summary.expired_with_recorded_disposition_total += report.lifecycle.lifecycle_existing_count
            summary.expired_terminal_dispositions_total += report.lifecycle.lifecycle_terminal_count
        outbox = report.outbox or {}
        outbox_delivered = int(outbox.get("delivered_count") or 0)
        outbox_retryable = int(outbox.get("retryable_failure_count") or 0)
        outbox_dead_letters = int(outbox.get("dead_letter_count") or 0)
        outbox_ack_failures = int(outbox.get("ack_failed_count") or 0)
        raw_outbox_errors = outbox.get("errors")
        outbox_error_count = (
            len(cast(list[object], raw_outbox_errors))
            if isinstance(raw_outbox_errors, list)
            else int(bool(raw_outbox_errors))
        )
        summary.outbox_delivered_total += outbox_delivered
        summary.outbox_retryable_failures_total += outbox_retryable
        summary.outbox_dead_letters_total += outbox_dead_letters
        summary.outbox_ack_failures_total += outbox_ack_failures
        required_processing = report.required_processing
        required_processing_failures = required_processing.failed_memory_ids if required_processing is not None else []
        if required_processing is not None and required_processing_failures:
            retryable_count = len(required_processing.retryable_memory_ids)
            quarantined_count = len(required_processing.quarantined_memory_ids)
            summary.errors.append(
                f"uid={uid}: required_processing_failed:"
                f"failed={len(required_processing_failures)}:"
                f"retryable={retryable_count}:"
                f"quarantined={quarantined_count}"
            )
        if report.required_intake and report.required_intake.failed_memory_ids:
            summary.errors.append(
                f"uid={uid}: required_intake_failed:count={len(report.required_intake.failed_memory_ids)}"
            )
        if report.observations and report.observations.error_code:
            summary.errors.append(f"uid={uid}: observation_intake_failed:{report.observations.error_code}")
        if outbox_retryable or outbox_dead_letters or outbox_ack_failures or outbox_error_count:
            summary.errors.append(
                f"uid={uid}: outbox_delivery_failed:"
                f"retryable={outbox_retryable}:"
                f"dead_letter={outbox_dead_letters}:"
                f"ack={outbox_ack_failures}:"
                f"errors={outbox_error_count}"
            )
        summary.maintained_users += 1
        if recurrence_inbox_drain is not None:
            try:
                summary.recurrence_receipts_delivered += await run_blocking(
                    db_executor, recurrence_inbox_drain, uid, firestore_client=client
                )
            except Exception as exc:
                summary.errors.append(f'uid={uid}: recurrence_delivery:{type(exc).__name__}')
        completed_uids.add(uid)
        logger.info(
            "canonical_short_term_maintenance_cron: uid=%s routed_count=%d promoted_count=%d skipped_reason=%s",
            uid,
            report.routed_count,
            promoted,
            skipped,
        )

    last_completed_registry_uid: Optional[str] = None
    for registry_uid in registry_uids:
        if registry_uid not in completed_uids:
            break
        last_completed_registry_uid = registry_uid
    if uid_inventory is None and last_completed_registry_uid:
        try:
            await run_blocking(
                db_executor,
                _persist_registry_cursor,
                client,
                last_completed_registry_uid,
                expected_generation=registry_cursor_generation,
            )
        except CanonicalMaintenanceInventoryUnavailable as exc:
            summary.errors.append(f"cursor_persist:{type(exc).__name__}")
            logger.warning(
                "canonical_short_term_maintenance_cron: cursor_persist_failed error=%s",
                type(exc).__name__,
            )

    logger.info(
        "canonical_short_term_maintenance_cron: done run_id=%s user_count=%d maintained_users=%d promoted_total=%d errors=%d",
        effective_run_id,
        summary.user_count,
        summary.maintained_users,
        summary.promoted_total,
        len(summary.errors),
    )
    summary.completed_uids = tuple(sorted(completed_uids))
    return summary
