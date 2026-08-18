"""Scheduled universal short-term maintenance (TTL audit + consolidation dreaming).

Hosted by the dedicated ``memory-maintenance-job`` Cloud Run Job
(``backend/modal/memory_maintenance_job.py``). The global maintenance switch
remains explicit. User selection comes only from a bounded injectable
inventory; this module never scans all users or consults a UID allowlist.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from typing import Any, Iterable, Optional, Protocol, cast

from pydantic import ValidationError

from database._client import db as default_db_client
from database.memory_collections import MemoryCollections
from models.product_memory import MemoryItemStatus, MemoryLayer
from utils.executors import db_executor, run_blocking
from utils.log_sanitizer import sanitize_validation_error
from utils.observability.fallback import record_fallback
from utils.memory.canonical_consolidation import CONSOLIDATION_ATTEMPT_LEASE_SECONDS
from utils.memory.short_term_promotion import (
    CanonicalShortTermMaintenanceReport,
    run_canonical_short_term_maintenance,
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
from scripts.enrich_historical_memory_graph import (
    MAX_PAGE_SIZE,
    MAX_STRUCTURED_SCAN_SIZE,
    run_enrichment,
)

logger = logging.getLogger(__name__)

MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV = "MEMORY_CANONICAL_MAINTENANCE_ENABLED"
MEMORY_CANONICAL_MAINTENANCE_FLEX_ENV = "MEMORY_CANONICAL_MAINTENANCE_FLEX"
MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED_ENV = "MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED"
MEMORY_CANONICAL_GRAPH_BACKFILL_PAGE_SIZE_ENV = "MEMORY_CANONICAL_GRAPH_BACKFILL_PAGE_SIZE"
MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE_ENV = "MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE"
DEFAULT_GRAPH_BACKFILL_PAGE_SIZE = 5
# The historical planner has a hard 20-second deadline per candidate.  Keep
# the scheduled scan to a small, page-relative look-ahead so one account
# cannot exhaust the Cloud Run Job's one-hour budget before later users run.
GRAPH_BACKFILL_SCAN_PAGE_MULTIPLIER = 5
DEFAULT_GRAPH_BACKFILL_SCAN_SIZE = DEFAULT_GRAPH_BACKFILL_PAGE_SIZE * GRAPH_BACKFILL_SCAN_PAGE_MULTIPLIER
MAX_MAINTENANCE_UIDS_PER_RUN = 400
CANONICAL_MEMORY_MAINTENANCE_SEED_CURSOR_PATH = "canonical_memory_maintenance_control/seed_cursor"
CANONICAL_MEMORY_MAINTENANCE_SEED_SCHEMA_VERSION = 1
CANONICAL_MEMORY_DREAMING_STATE_COLLECTION = "canonical_memory_dreaming_state"
DREAMING_MIN_INTERVAL = timedelta(hours=20)
OVERFLOW_SHORT_TERM_THRESHOLD = 10
ACTIVE_SHORT_TERM_COUNT_CAP = OVERFLOW_SHORT_TERM_THRESHOLD + 1
DREAMING_STATE_SCHEMA_VERSION = 1


class CanonicalMaintenanceInventoryUnavailable(RuntimeError):
    """The deployment did not provide a bounded UID inventory seam."""


class CanonicalMaintenanceUIDInventory(Protocol):
    def __call__(self, db_client: Any, limit: int) -> Iterable[str]: ...


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


def _read_registry_cursor(db_client: Any) -> str:
    ref = db_client.document(CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH)
    try:
        snapshot = ref.get()
    except Exception as exc:
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor unavailable") from exc
    if not getattr(snapshot, "exists", False):
        payload = {"schema_version": 1, "last_uid": ""}
        try:
            create = getattr(ref, "create", None)
            if callable(create):
                create(payload)
            else:
                ref.set(payload)
        except Exception as exc:
            raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor unavailable") from exc
        return ""
    payload = snapshot.to_dict()
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor is malformed")
    last_uid = payload.get("last_uid", "")
    if not isinstance(last_uid, str):
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor is malformed")
    return last_uid


def _persist_registry_cursor(db_client: Any, last_uid: str) -> None:
    payload = {"schema_version": 1, "last_uid": last_uid}
    try:
        db_client.document(CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH).set(payload, merge=True)
    except Exception as exc:
        raise CanonicalMaintenanceInventoryUnavailable("canonical maintenance cursor unavailable") from exc


def maintenance_flex_forced() -> bool:
    return os.getenv(MEMORY_CANONICAL_MAINTENANCE_FLEX_ENV, "false").lower() == "true"


def _dreaming_state_path(uid: str) -> str:
    return f"{CANONICAL_MEMORY_DREAMING_STATE_COLLECTION}/{uid}"


def _parse_dreamed_at(raw: object) -> Optional[datetime]:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str) and raw.strip():
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def read_last_dreamed_at(uid: str, *, db_client: Any) -> Optional[datetime]:
    try:
        snapshot = db_client.document(_dreaming_state_path(uid)).get()
    except Exception:
        return None
    if not getattr(snapshot, "exists", False):
        return None
    payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
    if not isinstance(payload, dict) or payload.get("schema_version") != DREAMING_STATE_SCHEMA_VERSION:
        return None
    return _parse_dreamed_at(payload.get("last_dreamed_at"))


def persist_last_dreamed_at(uid: str, *, db_client: Any, now: datetime) -> None:
    payload = {
        "uid": uid,
        "schema_version": DREAMING_STATE_SCHEMA_VERSION,
        "last_dreamed_at": now.astimezone(timezone.utc).isoformat(),
    }
    try:
        db_client.document(_dreaming_state_path(uid)).set(payload, merge=True)
    except Exception as exc:
        logger.warning(
            "canonical_short_term_maintenance_cron: dreaming_state_write_failed uid=%s error=%s",
            uid,
            type(exc).__name__,
        )


def count_active_short_term(uid: str, *, db_client: Any, cap: int = ACTIVE_SHORT_TERM_COUNT_CAP) -> Optional[int]:
    """Return how many active Short-term rows exist, capped at ``cap``.

    ``None`` means the query could not run. Callers fail open to "has work,
    not overflow" so a missing index cannot skip a user or mark the whole
    fleet as hourly overflow.
    """
    collection = getattr(db_client, "collection", None)
    if not callable(collection):
        return None
    try:
        query: Any = collection(MemoryCollections(uid=uid).memory_items)
        where = getattr(query, "where", None)
        if callable(where):
            query = where("tier", "==", MemoryLayer.short_term.value)
            query = query.where("status", "==", MemoryItemStatus.active.value)
        limit = getattr(query, "limit", None)
        if callable(limit):
            query = limit(max(1, cap))
        stream = getattr(query, "stream", None)
        if not callable(stream):
            return None
        return sum(1 for _ in cast(Iterable[object], stream()))
    except Exception:
        return None


def user_has_active_short_term(uid: str, *, db_client: Any) -> bool:
    """Return True when the account still has at least one active Short-term row.

    Fail open to True so a query/index miss cannot skip a user who still needs
    dreaming. Injected unit-test fakes without a collection API also keep work.
    """
    count = count_active_short_term(uid, db_client=db_client, cap=1)
    return True if count is None else count > 0


def recently_dreamed(uid: str, *, db_client: Any, now: datetime) -> bool:
    last_dreamed_at = read_last_dreamed_at(uid, db_client=db_client)
    if last_dreamed_at is None:
        return False
    return now - last_dreamed_at < DREAMING_MIN_INTERVAL


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
    cursor = _read_registry_cursor(db_client)
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
            _persist_registry_cursor(db_client, uids[-1])
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
    raw = os.getenv(MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "false")
    return raw.lower() == "true"


def canonical_graph_backfill_enabled() -> bool:
    """Keep graph migration work opt-in until the deployment contract enables it."""
    return os.getenv(MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED_ENV, "false").lower() == "true"


def canonical_graph_backfill_page_size() -> int:
    """Return the bounded per-user assertion-enrichment budget for one cron run."""
    raw = os.getenv(
        MEMORY_CANONICAL_GRAPH_BACKFILL_PAGE_SIZE_ENV,
        str(DEFAULT_GRAPH_BACKFILL_PAGE_SIZE),
    )
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_GRAPH_BACKFILL_PAGE_SIZE
    return min(MAX_PAGE_SIZE, max(1, value))


def canonical_graph_backfill_scan_size(*, page_size: int | None = None) -> int:
    """Return the cursor scan window, bounded to a small current-page multiple.

    The durable keyset cursor advances after every completed scan, so the cron
    no longer needs a corpus-sized candidate window to avoid rereading writes.
    Keep enough look-ahead to skip temporarily ineligible rows, but cap both
    the default and an explicit override at five current apply pages.  This
    bounds serial 20-second planner calls while retaining the global
    ``MAX_STRUCTURED_SCAN_SIZE`` ceiling.
    """
    current_page_size = page_size if page_size is not None else canonical_graph_backfill_page_size()
    current_page_size = min(MAX_PAGE_SIZE, max(1, current_page_size))
    maximum = min(
        MAX_STRUCTURED_SCAN_SIZE,
        current_page_size * GRAPH_BACKFILL_SCAN_PAGE_MULTIPLIER,
    )
    raw = os.getenv(
        MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE_ENV,
        str(DEFAULT_GRAPH_BACKFILL_SCAN_SIZE),
    )
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_GRAPH_BACKFILL_SCAN_SIZE
    return min(maximum, max(current_page_size, value))


@dataclass
class CanonicalShortTermMaintenanceCronSummary:
    run_id: str
    user_count: int = 0
    inventory_source: str = "bounded_registry"
    inventory_complete: bool = False
    routed_total: int = 0
    promoted_total: int = 0
    skipped_users: int = 0
    skipped_no_short_term: int = 0
    skipped_recently_dreamed: int = 0
    dreamed_users: int = 0
    flex_deferred: bool = False
    recurrence_candidates_total: int = 0
    outbox_delivered_total: int = 0
    outbox_retryable_failures_total: int = 0
    outbox_dead_letters_total: int = 0
    outbox_ack_failures_total: int = 0
    graph_enriched_total: int = 0
    graph_enrichment_blocked_total: int = 0
    errors: list[str] = field(default_factory=_empty_errors)


def _coerce_run_id(run_id: Optional[str], *, now: datetime) -> str:
    if run_id:
        return run_id
    return f'cron-{now.strftime("%Y%m%d%H%M%S")}'


def _skipped_reason(report: CanonicalShortTermMaintenanceReport) -> Optional[str]:
    if report.skipped_reason:
        return report.skipped_reason
    if report.consolidation and report.consolidation.skipped_reason:
        return report.consolidation.skipped_reason
    return None


def _promoted_count(report: CanonicalShortTermMaintenanceReport) -> int:
    return report.promoted_count


def _safe_maintenance_error(uid: str, exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return f"uid={uid}: ValidationError: {sanitize_validation_error(cast(Any, exc))}"
    return f"uid={uid}: {type(exc).__name__}"


def run_universal_short_term_maintenance(
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
    recurrence_signal_persister: Optional[Callable[..., int]] = None,
    recurrence_signal_consumer: Optional[Callable[..., int]] = None,
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
    promotion_flex = PromotionFlexRunRouter(db_client=client, force_enabled=maintenance_flex_forced())
    try:
        if uid_inventory is None:
            uids = bounded_canonical_memory_uid_inventory(client, limit=inventory_limit, persist_cursor=False)
        else:
            uids = _resolve_maintenance_uids(client, uid_inventory=uid_inventory, limit=inventory_limit)
    except CanonicalMaintenanceInventoryUnavailable as exc:
        message = "canonical_uid_inventory_unavailable"
        logger.warning(
            "canonical_short_term_maintenance_cron: %s (%s)",
            message,
            type(exc).__name__,
        )
        return CanonicalShortTermMaintenanceCronSummary(
            run_id=effective_run_id,
            inventory_source="unavailable",
            inventory_complete=False,
            errors=[message],
        )
    summary = CanonicalShortTermMaintenanceCronSummary(
        run_id=effective_run_id,
        user_count=len(uids),
        inventory_source="injected" if uid_inventory is not None else "bounded_registry",
        inventory_complete=True,
    )
    logger.info(
        "canonical_short_term_maintenance_cron: start run_id=%s user_count=%d flex=%s",
        effective_run_id,
        len(uids),
        promotion_flex.control.enabled,
    )
    last_completed_uid: Optional[str] = None
    for uid in uids:
        stm_count = count_active_short_term(uid, db_client=client)
        if stm_count == 0:
            summary.skipped_no_short_term += 1
            summary.skipped_users += 1
            last_completed_uid = uid
            logger.info("canonical_short_term_maintenance_cron: uid=%s skipped_reason=no_active_short_term", uid)
            continue
        overflow = stm_count is not None and stm_count > OVERFLOW_SHORT_TERM_THRESHOLD
        if recently_dreamed(uid, db_client=client, now=current_time) and not overflow:
            summary.skipped_recently_dreamed += 1
            summary.skipped_users += 1
            last_completed_uid = uid
            logger.info("canonical_short_term_maintenance_cron: uid=%s skipped_reason=recently_dreamed", uid)
            continue
        promotion_llm_invoke = promotion_flex.llm_invoke_for_uid(uid)
        try:
            report = run_canonical_short_term_maintenance(
                uid,
                db_client=client,
                now=maintenance_now,
                run_id=effective_run_id,
                recurrence_signal_sink=recurrence_signal_persister,
                required_processing_limit=0,
                llm_invoke=promotion_llm_invoke,
                consolidation_attempt_lease_seconds=(
                    MEMORY_PROMOTION_FLEX_LEASE_SECONDS
                    if promotion_llm_invoke is not None
                    else CONSOLIDATION_ATTEMPT_LEASE_SECONDS
                ),
                consolidation_result_guard=(
                    promotion_flex.assert_result_current if promotion_llm_invoke is not None else None
                ),
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
            last_completed_uid = uid
            continue

        promoted = _promoted_count(report)
        skipped = _skipped_reason(report)
        trigger = report.consolidation.trigger_reason if report.consolidation else None
        summary.routed_total += report.routed_count
        summary.promoted_total += promoted
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
        consolidation_errors = report.consolidation.errors if report.consolidation is not None else []
        consolidation_blocked = bool(report.consolidation and report.consolidation.watermark_blocked)
        if consolidation_blocked or consolidation_errors:
            retryable_count = len(report.consolidation.retryable_memory_ids) if report.consolidation is not None else 0
            quarantined_count = (
                len(report.consolidation.quarantined_memory_ids) if report.consolidation is not None else 0
            )
            summary.errors.append(
                f"uid={uid}: consolidation_failed:"
                f"blocked={int(consolidation_blocked)}:"
                f"retryable={retryable_count}:"
                f"quarantined={quarantined_count}:"
                f"errors={len(consolidation_errors)}"
            )
        if outbox_retryable or outbox_dead_letters or outbox_ack_failures or outbox_error_count:
            summary.errors.append(
                f"uid={uid}: outbox_delivery_failed:"
                f"retryable={outbox_retryable}:"
                f"dead_letter={outbox_dead_letters}:"
                f"ack={outbox_ack_failures}:"
                f"errors={outbox_error_count}"
            )
        if recurrence_signal_consumer is not None and report.consolidation is not None:
            try:
                summary.recurrence_candidates_total += recurrence_signal_consumer(
                    uid,
                    report.consolidation.recurrence_signals,
                    firestore_client=client,
                )
            except Exception as exc:
                message = f"uid={uid}: recurrence_consumer:{type(exc).__name__}"
                summary.errors.append(message)
                logger.warning("canonical_short_term_maintenance_cron: %s", message)
                record_fallback(
                    component="other",
                    from_mode="recurrence_maintenance",
                    to_mode="recurrence_inbox_retry",
                    reason="other",
                    outcome="degraded",
                )
        if report.routed_count == 0:
            summary.skipped_users += 1
        summary.dreamed_users += 1
        consolidation = report.consolidation
        dream_incomplete = bool(
            consolidation is not None
            and (consolidation.watermark_blocked or consolidation.errors or consolidation.retryable_memory_ids)
        )
        if not dream_incomplete:
            persist_last_dreamed_at(uid, db_client=client, now=current_time)
        last_completed_uid = uid

        logger.info(
            "canonical_short_term_maintenance_cron: uid=%s trigger_reason=%s routed_count=%d "
            "promoted_count=%d skipped_reason=%s",
            uid,
            trigger,
            report.routed_count,
            promoted,
            skipped,
        )

        if not canonical_graph_backfill_enabled():
            continue
        try:
            graph_page_size = canonical_graph_backfill_page_size()
            graph_report = run_enrichment(
                uid=uid,
                # The database client is injected above; this is retained only
                # for the CLI contract and is never used by this cron path.
                firestore_project=os.getenv("GOOGLE_CLOUD_PROJECT", "canonical-memory"),
                limit=graph_page_size,
                apply=True,
                confirm_uid=uid,
                structured_only=False,
                apply_limit=graph_page_size,
                scan_limit=canonical_graph_backfill_scan_size(page_size=graph_page_size),
                db_client=client,
            )
            graph_outcomes = graph_report.get("outcomes", {})
            summary.graph_enriched_total += int(graph_outcomes.get("committed", 0))
            summary.graph_enrichment_blocked_total += sum(
                int(value) for key, value in graph_outcomes.items() if key not in {"committed", "idempotent_skip"}
            )
        except Exception as exc:
            message = f"uid={uid}: graph_enrichment:{type(exc).__name__}"
            summary.errors.append(message)
            logger.warning("canonical_short_term_maintenance_cron: %s", message)

    if uid_inventory is None and last_completed_uid:
        try:
            _persist_registry_cursor(client, last_completed_uid)
        except CanonicalMaintenanceInventoryUnavailable as exc:
            summary.errors.append(f"cursor_persist:{type(exc).__name__}")
            logger.warning(
                "canonical_short_term_maintenance_cron: cursor_persist_failed error=%s",
                type(exc).__name__,
            )

    logger.info(
        "canonical_short_term_maintenance_cron: done run_id=%s user_count=%d routed_total=%d "
        "promoted_total=%d dreamed_users=%d skipped_no_short_term=%d skipped_recently_dreamed=%d "
        "flex_deferred=%s graph_enriched_total=%d graph_enrichment_blocked_total=%d skipped_users=%d errors=%d",
        effective_run_id,
        summary.user_count,
        summary.routed_total,
        summary.promoted_total,
        summary.dreamed_users,
        summary.skipped_no_short_term,
        summary.skipped_recently_dreamed,
        summary.flex_deferred,
        summary.graph_enriched_total,
        summary.graph_enrichment_blocked_total,
        summary.skipped_users,
        len(summary.errors),
    )
    return summary


async def run_canonical_short_term_maintenance_cron(
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
    recurrence_signal_persister: Optional[Callable[..., int]] = None,
    recurrence_signal_consumer: Optional[Callable[..., int]] = None,
    uid_inventory: Optional[CanonicalMaintenanceUIDInventory] = None,
    inventory_limit: int = MAX_MAINTENANCE_UIDS_PER_RUN,
) -> CanonicalShortTermMaintenanceCronSummary:
    """Async entrypoint: offload sync Firestore maintenance to ``db_executor``."""
    return await run_blocking(
        db_executor,
        run_universal_short_term_maintenance,
        db_client=db_client,
        now=now,
        run_id=run_id,
        recurrence_signal_persister=recurrence_signal_persister,
        recurrence_signal_consumer=recurrence_signal_consumer,
        uid_inventory=uid_inventory,
        inventory_limit=inventory_limit,
    )
