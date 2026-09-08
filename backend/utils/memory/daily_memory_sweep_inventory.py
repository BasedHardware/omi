"""Lifecycle-independent bounded UID inventory for the daily memory sweep.

This module intentionally has no import edge to canonical short-term
maintenance. Its registry seed, fair page cursors, onboarding discovery, and
durable retry queue remain deployable after the legacy maintenance job/image
is retired.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud import firestore

from database.firestore_index_registry import (
    DAILY_SWEEP_ONBOARDING_COMPLETED_USERS_QUERY,
    DAILY_SWEEP_ONBOARDING_DEVICE_COMPLETED_USERS_QUERY,
)

MAX_DAILY_SWEEP_UIDS_PER_PAGE = 400
# Keep retry work bounded to a slice of each page. A permanently failing first
# retry UID must not consume the whole page and starve fresh source pages.
MAX_DAILY_SWEEP_RETRY_UIDS_PER_PAGE = 32
MAX_JIT_QA_SWEEP_UIDS = 4
DAILY_SWEEP_CANONICAL_REGISTRY_COLLECTION = "daily_memory_sweep_registry"
DAILY_SWEEP_CANONICAL_CURSOR_PATH = "daily_memory_sweep_control/canonical_inventory_cursor"
DAILY_SWEEP_CANONICAL_REGISTRY_SCHEMA_VERSION = 1
DAILY_SWEEP_ONBOARDING_CURSOR_PATH = "daily_memory_sweep_control/onboarding_inventory_cursor"
DAILY_SWEEP_ONBOARDING_CURSOR_SCHEMA_VERSION = 1
DAILY_SWEEP_SEED_CURSOR_PATH = "daily_memory_sweep_control/seed_cursor"
DAILY_SWEEP_SEED_SCHEMA_VERSION = 1
DAILY_SWEEP_RETRY_COLLECTION = "daily_memory_sweep_control_retries"
DAILY_SWEEP_RETRY_STATE_SCHEMA_VERSION = 1
DAILY_SWEEP_RETRY_CURSOR_PATH = "daily_memory_sweep_control/retry_cursor"
DAILY_SWEEP_RETRY_CURSOR_SCHEMA_VERSION = 1


class DailySweepInventoryUnavailable(RuntimeError):
    """A bounded inventory or durable cursor could not be proven."""


class DailySweepUIDInventoryPage:
    def __init__(
        self,
        *,
        uids: tuple[str, ...],
        canonical_uids: tuple[str, ...] = (),
        onboarding_uids: tuple[str, ...] = (),
        retry_uids: tuple[str, ...] = (),
        canonical_cursor_generation: int = 0,
        onboarding_cursor_generation: int = 0,
        retry_cursor_generation: int = 0,
    ) -> None:
        self.uids = uids
        self.canonical_uids = canonical_uids
        self.onboarding_uids = onboarding_uids
        self.retry_uids = retry_uids
        self.canonical_cursor_generation = canonical_cursor_generation
        self.onboarding_cursor_generation = onboarding_cursor_generation
        self.retry_cursor_generation = retry_cursor_generation


def explicit_jit_qa_daily_sweep_uid_inventory(
    uids: Iterable[object],
) -> DailySweepUIDInventoryPage:
    """Build a bounded QA page without touching the global inventory/cursors.

    The isolated QA job must never scan shared ``memory_state`` or mutate the
    normal sweep cursors.  Keep this helper independent of Firestore so tests
    can prove that a QA execution cannot accidentally fall back to a global
    inventory query.
    """

    normalized: list[str] = []
    for value in uids:
        uid = value.strip() if isinstance(value, str) else ""
        if not uid or "/" in uid or uid in normalized:
            if uid and uid in normalized:
                continue
            raise DailySweepInventoryUnavailable("JIT QA sweep allowlist contains an invalid UID")
        normalized.append(uid)
    if not normalized or len(normalized) > MAX_JIT_QA_SWEEP_UIDS:
        raise DailySweepInventoryUnavailable("JIT QA sweep requires one to four explicit UIDs")
    return DailySweepUIDInventoryPage(uids=tuple(normalized))


def _read_payload(ref: Any) -> dict[str, Any]:
    try:
        snapshot = ref.get()
    except Exception as exc:
        raise DailySweepInventoryUnavailable("daily sweep control state unavailable") from exc
    if not getattr(snapshot, "exists", False):
        return {}
    payload = snapshot.to_dict()
    if not isinstance(payload, dict):
        raise DailySweepInventoryUnavailable("daily sweep control state malformed")
    return cast(dict[str, Any], payload)


def _read_cursor_state(db_client: Any, path: str, schema_version: int) -> tuple[str, int]:
    payload = _read_payload(db_client.document(path))
    if payload and payload.get("schema_version") != schema_version:
        raise DailySweepInventoryUnavailable("daily sweep cursor malformed")
    value = payload.get("last_uid", "")
    if not isinstance(value, str):
        raise DailySweepInventoryUnavailable("daily sweep cursor malformed")
    generation = payload.get("generation", 0)
    if not isinstance(generation, int) or generation < 0:
        raise DailySweepInventoryUnavailable("daily sweep cursor malformed")
    return value.strip(), generation


def _write_cursor(
    db_client: Any,
    path: str,
    schema_version: int,
    last_uid: str,
    *,
    expected_generation: int | None = None,
) -> None:
    try:
        ref = db_client.document(path)
        current_payload = _read_payload(ref)
        current_generation = current_payload.get("generation", 0)
        current_uid = current_payload.get("last_uid", "")
        if not isinstance(current_generation, int) or current_generation < 0 or not isinstance(current_uid, str):
            raise DailySweepInventoryUnavailable("daily sweep cursor malformed")
        if expected_generation is not None and current_generation != expected_generation:
            raise DailySweepInventoryUnavailable("daily sweep cursor generation conflict")
        payload = {
            "schema_version": schema_version,
            "last_uid": last_uid,
            "generation": current_generation + 1,
        }
        # Production Firestore uses a transaction so two overlapping workers
        # cannot both observe the same generation and then overwrite one
        # another. Small fakes may not support transactional reads; retain the
        # CAS read/write fallback for those hermetic seams.
        transaction_factory = getattr(db_client, "transaction", None)
        if callable(transaction_factory):
            try:
                transaction = transaction_factory()

                def write_transaction(tx: Any) -> None:
                    snapshot = ref.get(transaction=tx)
                    live = snapshot.to_dict() if getattr(snapshot, "exists", False) else {}
                    live_generation = live.get("generation", 0) if isinstance(live, dict) else 0
                    if live_generation != current_generation:
                        raise DailySweepInventoryUnavailable("daily sweep cursor generation conflict")
                    tx.set(ref, payload, merge=True)

                cast(Any, firestore.transactional(write_transaction))(transaction)
                return
            except TypeError:
                pass
        ref.set(payload, merge=True)
    except Exception as exc:
        raise DailySweepInventoryUnavailable("daily sweep cursor unavailable") from exc


def _read_retry_uids(db_client: Any, *, limit: int) -> tuple[str, ...]:
    """Read a rotating bounded retry page without dropping malformed state."""

    try:
        cursor, _generation = _read_cursor_state(
            db_client, DAILY_SWEEP_RETRY_CURSOR_PATH, DAILY_SWEEP_RETRY_CURSOR_SCHEMA_VERSION
        )
        collection = db_client.collection(DAILY_SWEEP_RETRY_COLLECTION)
        query = collection.where("uid", ">", cursor) if cursor else collection
        snapshots = query.order_by("uid").limit(limit).stream()
        page = list(snapshots)
        if cursor and len(page) < limit:
            page.extend(collection.order_by("uid").limit(limit - len(page)).stream())
        retry_uids: list[str] = []
        for snapshot in page:
            payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
            if not isinstance(payload, dict):
                raise DailySweepInventoryUnavailable("daily sweep retry state malformed")
            if payload.get("schema_version") != DAILY_SWEEP_RETRY_STATE_SCHEMA_VERSION:
                raise DailySweepInventoryUnavailable("daily sweep retry state malformed")
            uid = payload.get("uid")
            if not isinstance(uid, str) or not uid.strip() or "/" in uid:
                raise DailySweepInventoryUnavailable("daily sweep retry state malformed")
            normalized_uid = uid.strip()
            if normalized_uid not in retry_uids:
                retry_uids.append(normalized_uid)
        return tuple(retry_uids)
    except DailySweepInventoryUnavailable:
        raise
    except Exception as exc:
        raise DailySweepInventoryUnavailable("daily sweep retry state unavailable") from exc


def _seed_registry(db_client: Any, *, limit: int) -> None:
    collection_group_factory = getattr(db_client, "collection_group", None)
    if not callable(collection_group_factory):
        return
    seed_cursor, seed_generation = _read_cursor_state(
        db_client, DAILY_SWEEP_SEED_CURSOR_PATH, DAILY_SWEEP_SEED_SCHEMA_VERSION
    )
    cursor_snapshot = None
    if seed_cursor:
        try:
            candidate = db_client.document(seed_cursor).get()
        except Exception as exc:
            raise DailySweepInventoryUnavailable("daily sweep seed cursor unavailable") from exc
        if getattr(candidate, "exists", False):
            cursor_snapshot = candidate
    try:
        query: Any = cast(Any, collection_group_factory("memory_state")).order_by("__name__")
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        page = list(query.limit(limit).stream())
        if not page and cursor_snapshot is not None:
            page = list(cast(Any, collection_group_factory("memory_state")).order_by("__name__").limit(limit).stream())
        last_path = seed_cursor
        for snapshot in page:
            path = str(getattr(getattr(snapshot, "reference", None), "path", ""))
            parts = path.split("/")
            if len(parts) != 4 or parts[0] != "users" or parts[2:] != ["memory_state", "apply_control"]:
                last_path = path or last_path
                continue
            uid = parts[1]
            payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
            if not isinstance(payload, dict) or payload.get("uid") != uid or not uid or "/" in uid:
                raise DailySweepInventoryUnavailable("daily sweep seed row malformed")
            db_client.document(f"{DAILY_SWEEP_CANONICAL_REGISTRY_COLLECTION}/{uid}").set(
                {"uid": uid, "schema_version": DAILY_SWEEP_CANONICAL_REGISTRY_SCHEMA_VERSION},
                merge=True,
            )
            last_path = path
        if page:
            _write_cursor(
                db_client,
                DAILY_SWEEP_SEED_CURSOR_PATH,
                DAILY_SWEEP_SEED_SCHEMA_VERSION,
                last_path,
                expected_generation=seed_generation,
            )
    except DailySweepInventoryUnavailable:
        raise
    except Exception as exc:
        raise DailySweepInventoryUnavailable("daily sweep registry seed failed") from exc


def bounded_canonical_daily_sweep_uids(
    db_client: Any,
    *,
    limit: int,
    persist_cursor: bool,
) -> tuple[str, ...]:
    bounded_limit = max(1, min(MAX_DAILY_SWEEP_UIDS_PER_PAGE, int(limit)))
    collection = getattr(db_client, "collection", None)
    if not callable(collection):
        raise DailySweepInventoryUnavailable("daily sweep registry unavailable")
    _seed_registry(db_client, limit=bounded_limit)
    cursor, cursor_generation = _read_cursor_state(
        db_client, DAILY_SWEEP_CANONICAL_CURSOR_PATH, DAILY_SWEEP_CANONICAL_REGISTRY_SCHEMA_VERSION
    )
    try:
        registry = cast(Any, collection(DAILY_SWEEP_CANONICAL_REGISTRY_COLLECTION))
        query = registry.where("uid", ">", cursor) if cursor else registry
        page = list(query.order_by("uid").limit(bounded_limit).stream())
        if cursor and len(page) < bounded_limit:
            page.extend(list(registry.order_by("uid").limit(bounded_limit - len(page)).stream()))
        uids: list[str] = []
        for snapshot in page:
            payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
            uid = payload.get("uid") if isinstance(payload, dict) else None
            if not isinstance(uid, str) or not uid.strip() or "/" in uid:
                raise DailySweepInventoryUnavailable("daily sweep registry row malformed")
            if uid not in uids:
                uids.append(uid.strip())
        if persist_cursor and uids:
            _write_cursor(
                db_client,
                DAILY_SWEEP_CANONICAL_CURSOR_PATH,
                DAILY_SWEEP_CANONICAL_REGISTRY_SCHEMA_VERSION,
                uids[-1],
                expected_generation=cursor_generation,
            )
        return tuple(uids)
    except DailySweepInventoryUnavailable:
        raise
    except Exception as exc:
        raise DailySweepInventoryUnavailable("daily sweep registry query failed") from exc


def bounded_daily_memory_sweep_uid_inventory(
    db_client: Any,
    *,
    limit: int = MAX_DAILY_SWEEP_UIDS_PER_PAGE,
    persist_cursor: bool = False,
    return_page: bool = False,
) -> tuple[str, ...] | DailySweepUIDInventoryPage:
    bounded_limit = max(1, min(MAX_DAILY_SWEEP_UIDS_PER_PAGE, int(limit)))
    retry_limit = max(1, min(MAX_DAILY_SWEEP_RETRY_UIDS_PER_PAGE, bounded_limit // 4))
    retry_uids = _read_retry_uids(db_client, limit=retry_limit)
    _retry_cursor, retry_cursor_generation = _read_cursor_state(
        db_client, DAILY_SWEEP_RETRY_CURSOR_PATH, DAILY_SWEEP_RETRY_CURSOR_SCHEMA_VERSION
    )
    remaining = bounded_limit - len(retry_uids)
    if remaining:
        onboarding_limit = max(1, remaining // 2) if remaining > 1 else 1
        canonical_limit = max(0, remaining - onboarding_limit)
        canonical = (
            bounded_canonical_daily_sweep_uids(db_client, limit=canonical_limit, persist_cursor=persist_cursor)
            if canonical_limit
            else ()
        )
    else:
        canonical = ()
        onboarding_limit = 0
    discovered: list[str] = list(retry_uids)
    for uid in canonical:
        if uid not in discovered:
            discovered.append(uid)
    onboarding: tuple[str, ...] = ()
    onboarding_cursor_generation = 0
    users = getattr(db_client, "collection", lambda _name: None)("users")
    where = getattr(users, "where", None)
    if remaining and callable(where):
        onboarding_cursor, onboarding_cursor_generation = _read_cursor_state(
            db_client, DAILY_SWEEP_ONBOARDING_CURSOR_PATH, DAILY_SWEEP_ONBOARDING_CURSOR_SCHEMA_VERSION
        )
        rows: list[str] = []
        for field_name, query_spec in (
            ("onboarding.completed", DAILY_SWEEP_ONBOARDING_COMPLETED_USERS_QUERY),
            (
                "onboarding.device_onboarding_completed",
                DAILY_SWEEP_ONBOARDING_DEVICE_COMPLETED_USERS_QUERY,
            ),
        ):
            try:
                if onboarding_cursor:
                    # Firestore's __name__ operand is a Key, not the document ID
                    # string. A bare UID is rejected with InvalidArgument before
                    # any onboarding row can be inventoried.
                    document_factory = getattr(users, "document", None)
                    after_uid = document_factory(onboarding_cursor) if callable(document_factory) else onboarding_cursor
                    query: Any = query_spec.build(
                        users,
                        {"completed": True, "after_uid": after_uid},
                        field_filter_factory=FieldFilter,
                    )
                else:
                    # There is no valid empty document reference. The first page
                    # needs only the onboarding predicate; later pages add the
                    # server-side document-ID cursor above.
                    query = cast(Any, where)(filter=FieldFilter(field_name, "==", True))
            except (TypeError, ValueError):
                # Keep compatibility with small Firestore fakes and older
                # client releases that do not accept FieldFilter as a kwarg.
                query = cast(Any, where)(field_name, "==", True)
                if onboarding_cursor:
                    document_factory = getattr(users, "document", None)
                    after_uid = document_factory(onboarding_cursor) if callable(document_factory) else onboarding_cursor
                    try:
                        query = query.where(FieldPath.document_id(), ">", after_uid)
                    except TypeError:
                        query = query.where(filter=FieldFilter(FieldPath.document_id(), ">", after_uid))
            try:
                query = query.order_by("__name__")
            except (AttributeError, TypeError):
                pass
            for snapshot in query.limit(onboarding_limit).stream():
                uid = str(getattr(snapshot, "id", "") or "").strip()
                if uid and "/" not in uid and uid not in rows:
                    rows.append(uid)
        rows.sort()
        onboarding = tuple(rows[:onboarding_limit])
        for uid in onboarding:
            if uid not in discovered:
                discovered.append(uid)
    elif remaining:
        raise DailySweepInventoryUnavailable("onboarding inventory unavailable")
    page = DailySweepUIDInventoryPage(
        uids=tuple(discovered[:bounded_limit]),
        canonical_uids=tuple(uid for uid in canonical if uid in discovered[:bounded_limit]),
        onboarding_uids=tuple(uid for uid in onboarding if uid in discovered[:bounded_limit]),
        retry_uids=retry_uids,
        canonical_cursor_generation=_read_cursor_state(
            db_client, DAILY_SWEEP_CANONICAL_CURSOR_PATH, DAILY_SWEEP_CANONICAL_REGISTRY_SCHEMA_VERSION
        )[1],
        onboarding_cursor_generation=onboarding_cursor_generation if remaining else 0,
        retry_cursor_generation=retry_cursor_generation,
    )
    return page if return_page else page.uids


def commit_daily_memory_sweep_uid_inventory(
    db_client: Any,
    page: DailySweepUIDInventoryPage,
    *,
    completed_uids: Iterable[str],
    failed_uids: Iterable[str] = (),
    advance_page: bool = True,
) -> None:
    completed = {uid.strip() for uid in completed_uids if uid.strip()}
    failed = {uid.strip() for uid in failed_uids if uid.strip()}
    # A failure always wins an ambiguous caller result; never delete a retry
    # receipt for a UID that also appears in the failure set.
    completed.difference_update(failed)
    if not advance_page and not completed and not failed:
        return
    try:
        # Per-UID documents avoid bounded-array overflow and concurrent
        # read/modify/write loss. Persist retries before advancing cursors.
        for uid in sorted(failed):
            db_client.document(f"{DAILY_SWEEP_RETRY_COLLECTION}/{uid}").set(
                {"schema_version": DAILY_SWEEP_RETRY_STATE_SCHEMA_VERSION, "uid": uid},
                merge=True,
            )
        for uid in sorted(completed):
            db_client.document(f"{DAILY_SWEEP_RETRY_COLLECTION}/{uid}").delete()
    except Exception as exc:
        raise DailySweepInventoryUnavailable("daily sweep retry state unavailable") from exc
    if page.retry_uids:
        _write_cursor(
            db_client,
            DAILY_SWEEP_RETRY_CURSOR_PATH,
            DAILY_SWEEP_RETRY_CURSOR_SCHEMA_VERSION,
            page.retry_uids[-1],
            expected_generation=page.retry_cursor_generation,
        )
    if advance_page and page.canonical_uids:
        _write_cursor(
            db_client,
            DAILY_SWEEP_CANONICAL_CURSOR_PATH,
            DAILY_SWEEP_CANONICAL_REGISTRY_SCHEMA_VERSION,
            page.canonical_uids[-1],
            expected_generation=page.canonical_cursor_generation,
        )
    if advance_page and page.onboarding_uids:
        _write_cursor(
            db_client,
            DAILY_SWEEP_ONBOARDING_CURSOR_PATH,
            DAILY_SWEEP_ONBOARDING_CURSOR_SCHEMA_VERSION,
            page.onboarding_uids[-1],
            expected_generation=page.onboarding_cursor_generation,
        )
