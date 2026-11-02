"""Store-wide oldest-ready age samples. Kept off ``durable_queue.py`` so isolated
tests can load policy/redrive without the Firestore SDK.
"""

from __future__ import annotations

import math
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from google.cloud.firestore_v1 import FieldFilter
from prometheus_client import Counter, Gauge

from config.firestore_read_levers import lever_enabled
from database._client import get_firestore_client
from utils.durable_queue_policy import oldest_ready_age_seconds
from utils.other.fsr_leader_lease import check_leader_lease, LeaseLost, queue_age_publisher_eligible

# Metadata-only reads: at most 5 pages x 200 rows per status. Document-name
# order is not age order; reaching the cap cannot prove the oldest ready age.
_STORE_WIDE_PAGE = 200
_STORE_WIDE_MAX_PAGES = 5

# Keep aligned with the durable-queue alert in monitoring/alerts/resilience.json.
_ALERT_AGE_SECONDS = 21600
_sample_cache: Optional[tuple[float, Dict[str, Optional[float]]]] = None
_sample_cache_lock = threading.RLock()
QUEUE_AGE_BUDGET_EVENTS = Counter(
    'omi_queue_age_budget_events_total',
    'Budgeted queue-age publisher outcomes.',
    ['outcome'],
)
QUEUE_AGE_SAMPLE_TIMESTAMP = Gauge(
    'omi_queue_age_sample_timestamp_seconds',
    'Unix time of the last fresh budgeted queue-age scan; cache hits do not refresh it.',
)


def _sample_budget_enabled() -> bool:
    try:
        key = os.getenv('HOSTNAME') or f"{os.getenv('K_REVISION', '')}:{socket.gethostname()}"
        return lever_enabled('queue_age_sample_budget', key)
    except ValueError:
        # An unregistered lever must preserve the off path.
        return False


def _min_publish_seconds() -> float:
    try:
        seconds = float(os.getenv('FSR_QUEUE_AGE_MIN_PUBLISH_SECONDS', '300'))
        if math.isfinite(seconds) and seconds > 0:
            return seconds
    except ValueError:
        pass
    return 300.0


# Checked-in sampler inventory. Must stay aligned with utils.metrics.OMI_QUEUE_NAMES.
QUEUE_AGE_SAMPLERS: Dict[str, Dict[str, Any]] = {
    'memory_outbox': {
        'collection': 'memory_outbox',
        'status_field': 'status',
        'ready_statuses': ('pending', 'retryable_failure', 'processing'),
        'created_at_field': 'created_at',
        # Canonical events lack created_at; lease/claim/availability timestamps
        # are conservative lower bounds on age, not original creation times.
        'age_fallback_fields': ('queued_at', 'lease_expires_at', 'claimed_at', 'available_at'),
        'collection_group': True,
    },
    'candidate_integration_outbox': {
        'collection': 'candidate_integration_outbox',
        'status_field': 'status',
        'ready_statuses': ('pending', 'failed', 'processing'),
        'created_at_field': 'created_at',
        'collection_group': True,
    },
    'vector_repair_outbox': {
        'collection': 'memory_outbox',
        'status_field': 'status',
        'ready_statuses': ('pending', 'in_progress'),
        'created_at_field': 'queued_at',
        'event_type': 'vector_repair_purge',
        'collection_group': True,
    },
    'task_recurrence_inbox': {
        'collection': 'task_recurrence_inbox',
        'status_field': 'status',
        'ready_statuses': ('pending',),
        'created_at_field': 'created_at',
        'collection_group': True,
    },
    'frame_deletion_outbox': {
        'collection': 'frame_deletion_outbox',
        'status_field': None,
        'ready_statuses': (),
        'created_at_field': 'created_at',
        'collection_group': True,
    },
    'daily_summary_hour_groups': {'ephemeral': True},
    'conversation_finalization_jobs': {'summary': True},
}


def _utc_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime):
        raise ValueError('invalid queue timestamp')
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _created_ats_from_page(
    snapshots: Iterable[Any],
    *,
    created_at_field: str,
    event_type: Optional[str] = None,
    age_fallback_fields: Iterable[str] = (),
    now: Optional[datetime] = None,
    failures: Optional[List[bool]] = None,
) -> List[datetime]:
    created_ats: List[datetime] = []
    for snapshot in snapshots:
        try:
            payload = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else snapshot
            if not isinstance(payload, dict):
                raise ValueError('invalid queue metadata')
            if event_type is not None and payload.get('event_type') != event_type:
                continue
            leased = payload.get('status') in {'processing', 'in_progress'}
            if now is not None and leased:
                lease_expires_at = _utc_timestamp(payload.get('lease_expires_at'))
                if lease_expires_at is not None:
                    if lease_expires_at > now:
                        continue
                else:
                    claimed_at = _utc_timestamp(payload.get('claimed_at'))
                    if claimed_at is not None and claimed_at + timedelta(seconds=300) > now:
                        continue
            if now is not None and not leased:
                available_at = _utc_timestamp(payload.get('available_at'))
                if available_at is not None and available_at > now:
                    continue
            created_at = _utc_timestamp(payload.get(created_at_field))
            for field in age_fallback_fields:
                if created_at is not None:
                    break
                created_at = _utc_timestamp(payload.get(field))
            if created_at is None:
                raise ValueError('missing queue creation timestamp')
            created_ats.append(created_at)
        except Exception:
            # A malformed document cannot hide healthy work in the same page.
            # It also prevents an otherwise empty sample from proving age zero.
            if failures is not None:
                failures.append(True)
    return created_ats


def _sample_status_page(client: Any, spec: Mapping[str, Any], *, now: datetime) -> Optional[List[datetime]]:
    budget_enabled = _sample_budget_enabled()
    collection = str(spec['collection'])
    created_at_field = str(spec['created_at_field'])
    event_type = spec.get('event_type')
    age_fallback_fields = tuple(spec.get('age_fallback_fields') or ())
    status_field = spec.get('status_field')
    ready_statuses: tuple[Any, ...] = tuple(spec.get('ready_statuses') or ())
    created_ats: List[datetime] = []
    failures: List[bool] = []
    exhausted = True
    for status in ready_statuses or (None,):
        query = client.collection_group(collection)
        if status_field and status is not None:
            query = query.where(filter=FieldFilter(status_field, '==', status))
        # Keep the declared equality-only group query. Firestore's implicit
        # document-name ordering plus snapshot cursors needs no new composite.
        query = query.select(
            list(
                dict.fromkeys(
                    [
                        created_at_field,
                        *age_fallback_fields,
                        'event_type',
                        'available_at',
                        'status',
                        'claimed_at',
                        'lease_expires_at',
                    ]
                )
            )
        )
        for page in range(_STORE_WIDE_MAX_PAGES):
            check_leader_lease()
            snapshots = list(query.limit(_STORE_WIDE_PAGE).stream())
            page_created_ats = _created_ats_from_page(
                snapshots,
                created_at_field=created_at_field,
                event_type=event_type,
                age_fallback_fields=age_fallback_fields,
                now=now,
                failures=failures,
            )
            created_ats.extend(page_created_ats)
            if (
                budget_enabled
                and page == 0
                and len(snapshots) == _STORE_WIDE_PAGE
                and not failures
                and page_created_ats
                and (now - min(page_created_ats)).total_seconds() > _ALERT_AGE_SECONDS
            ):
                # Document-name order cannot prove the true oldest. This is a
                # lower bound already breaching the alert; small/zero ages still
                # require exhaustion, and hitting the page cap remains unknown.
                QUEUE_AGE_BUDGET_EVENTS.labels(outcome='early_stop').inc()
                break
            if len(snapshots) < _STORE_WIDE_PAGE:
                break
            if page == _STORE_WIDE_MAX_PAGES - 1:
                exhausted = False
            else:
                query = query.start_after(snapshots[-1])
    # Even with ready rows observed, skipped event types can hide older work
    # beyond the cap. Zero additionally requires no uninspectable documents.
    if not exhausted or (failures and (budget_enabled or not created_ats)):
        return None
    return created_ats


def sample_store_wide_oldest_ready_ages(
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
    finalization_summary: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Optional[float]]:
    """Store-wide oldest-ready age per queue. Missing key = unknown; the publisher removes stale age and marks unknown.

    ``None`` values prove no ready item after exhausting all status queries.
    Every capped scan omits the key, even if it found some ready work. With the
    sample budget enabled, ages above the alert threshold may be lower bounds.
    """
    observed = _utc_timestamp(now) or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ages: Dict[str, Optional[float]] = {}
    for queue, spec in QUEUE_AGE_SAMPLERS.items():
        check_leader_lease()
        try:
            if spec.get('ephemeral'):
                ages[queue] = 0.0
                continue
            if spec.get('summary'):
                if finalization_summary is None:
                    continue
                ages[queue] = float(finalization_summary.get('oldest_nonterminal_age_seconds') or 0.0)
                continue
            created_ats = _sample_status_page(client, spec, now=observed)
            if created_ats is not None:
                ages[queue] = oldest_ready_age_seconds(created_ats, now=observed)
        except LeaseLost:
            raise
        except Exception:
            continue
    return ages


def publish_all_queue_oldest_ready_ages(
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
    finalization_summary: Optional[Mapping[str, Any]] = None,
) -> None:
    """Periodic publisher. Call from the service metrics tick only, never a request path."""
    if _sample_budget_enabled():
        with _sample_cache_lock:
            try:
                _publish_queue_ages(
                    now=now,
                    firestore_client=firestore_client,
                    finalization_summary=finalization_summary,
                    budget_enabled=True,
                )
            except Exception:
                withdraw_queue_oldest_ready_ages()
                raise
        return
    # Disabling the lever invalidates any prior cohort's cached observations.
    global _sample_cache
    _sample_cache = None
    _publish_queue_ages(now=now, firestore_client=firestore_client, finalization_summary=finalization_summary)


def _publish_queue_ages(
    *,
    now: Optional[datetime],
    firestore_client: Any,
    finalization_summary: Optional[Mapping[str, Any]],
    budget_enabled: bool = False,
) -> None:
    global _sample_cache
    from utils.durable_queue_metrics import publish_sampled_queue_oldest_ready_ages

    if not queue_age_publisher_eligible():
        withdraw_queue_oldest_ready_ages()
        return
    check_leader_lease()
    started = time.monotonic() if budget_enabled else 0.0
    if budget_enabled and _sample_cache is not None and 0 <= started - _sample_cache[0] < _min_publish_seconds():
        check_leader_lease(require_ownership=True)
        if not queue_age_publisher_eligible():
            withdraw_queue_oldest_ready_ages()
            return
        publish_sampled_queue_oldest_ready_ages(_sample_cache[1])
        QUEUE_AGE_BUDGET_EVENTS.labels(outcome='cache_hit').inc()
        return
    if budget_enabled:
        # A stalled fresh scan must not leave an expired age (especially zero)
        # visible to scrapes. Only a completed scan can replace unknown or
        # advance the fresh-scan timestamp; invalidate before any summary I/O.
        check_leader_lease(require_ownership=True)
        _sample_cache = None
        publish_sampled_queue_oldest_ready_ages({})
    sample_time = (_utc_timestamp(now) or datetime.now(timezone.utc)) if budget_enabled else now
    summary = finalization_summary
    if summary is None:
        try:
            from database.conversation_finalization_jobs import get_finalization_job_summary

            summary = get_finalization_job_summary(firestore_client=firestore_client)
        except LeaseLost:
            raise
        except Exception:
            summary = None
    check_leader_lease()
    ages = sample_store_wide_oldest_ready_ages(
        now=sample_time,
        firestore_client=firestore_client,
        finalization_summary=summary,
    )
    check_leader_lease(require_ownership=True)
    if not queue_age_publisher_eligible():
        withdraw_queue_oldest_ready_ages()
        return
    publish_sampled_queue_oldest_ready_ages(ages)
    if budget_enabled:
        # Age the cache from scan START, so slow scans cannot extend freshness.
        _sample_cache = (started, ages)
        QUEUE_AGE_BUDGET_EVENTS.labels(outcome='scan').inc()
        assert sample_time is not None
        QUEUE_AGE_SAMPLE_TIMESTAMP.set(sample_time.timestamp())


def withdraw_queue_oldest_ready_ages() -> None:
    """A former publisher must not leave stale gauges on a still-scraped pod."""
    from utils.metrics import OMI_QUEUE_NAMES, OMI_QUEUE_OLDEST_READY_AGE_SECONDS, OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN

    global _sample_cache
    with _sample_cache_lock:
        _sample_cache = None
        for queue in OMI_QUEUE_NAMES:
            for gauge in (OMI_QUEUE_OLDEST_READY_AGE_SECONDS, OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN):
                try:
                    gauge.remove(queue)
                except KeyError:
                    pass
