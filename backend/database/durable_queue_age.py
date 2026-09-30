"""Store-wide oldest-ready age samples. Kept off ``durable_queue.py`` so isolated
tests can load policy/redrive without the Firestore SDK.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from utils.durable_queue_policy import oldest_ready_age_seconds

logger = logging.getLogger(__name__)

_STORE_WIDE_PAGE = 200

# Checked-in sampler inventory. Must stay aligned with utils.metrics.OMI_QUEUE_NAMES.
QUEUE_AGE_SAMPLERS: Dict[str, Dict[str, Any]] = {
    'memory_outbox': {
        'collection': 'memory_outbox',
        'status_field': 'status',
        'ready_statuses': ('pending', 'retryable_failure'),
        'created_at_field': 'created_at',
        'collection_group': True,
    },
    'candidate_integration_outbox': {
        'collection': 'candidate_integration_outbox',
        'status_field': 'status',
        'ready_statuses': ('pending', 'failed', 'processing'),
        'created_at_field': 'created_at',
        'collection_group': True,
    },
    'chat_first_proactive_intents': {
        'collection': 'chat_first_proactive_intents',
        'status_field': 'delivery_state',
        'ready_statuses': ('ready', 'pending_kernel_receipt'),
        'created_at_field': 'created_at',
        'collection_group': True,
    },
    'vector_repair_outbox': {
        'collection': 'memory_outbox',
        'status_field': 'status',
        'ready_statuses': ('pending',),
        'created_at_field': 'created_at',
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
    'projection_repairs': {
        'collection': 'projection_repairs',
        'status_field': 'status',
        'ready_statuses': ('queued', 'failed'),
        'created_at_field': 'created_at',
        'collection_group': True,
    },
    'daily_summary_hour_groups': {'ephemeral': True},
    'daily_memory_sweep': {'ephemeral': True},
    'conversation_finalization_jobs': {'summary': True},
}


def _parse_created_at(value: Any) -> datetime | None:
    """Normalize timestamp representation to timezone-aware UTC datetime.

    Supports datetime instances (naive or aware), ISO-8601 strings, and Unix epoch timestamps.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            try:
                dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            flt = float(value)
            if not math.isnan(flt) and not math.isinf(flt) and 0 < flt < 1e11:
                return datetime.fromtimestamp(flt, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _created_ats_from_page(
    snapshots: Optional[Iterable[Any]],
    *,
    created_at_field: str,
    event_type: Optional[str] = None,
) -> List[datetime]:
    created_ats: List[datetime] = []
    if snapshots is None:
        return created_ats
    try:
        for snapshot in snapshots:
            try:
                payload = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else snapshot
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if event_type is not None and payload.get('event_type') != event_type:
                continue
            created_at = _parse_created_at(payload.get(created_at_field))
            if created_at is not None:
                created_ats.append(created_at)
    except Exception as exc:
        logger.warning("Error reading snapshots page: %s", exc)
    return created_ats


def _sample_status_page(
    client: Any,
    spec: Mapping[str, Any],
    page_size: int = _STORE_WIDE_PAGE,
) -> List[datetime]:
    if client is None or not hasattr(client, 'collection_group'):
        raise RuntimeError('Firestore client unavailable or missing collection_group')
    collection = str(spec['collection'])
    created_at_field = str(spec.get('created_at_field') or 'created_at')

    limit = max(1, min(page_size, 1000))
    event_type = spec.get('event_type')
    status_field = spec.get('status_field')
    ready_statuses: tuple[Any, ...] = tuple(spec.get('ready_statuses') or ())
    created_ats: List[datetime] = []

    if status_field and ready_statuses:
        for status in ready_statuses:
            query = (
                client.collection_group(collection).where(filter=FieldFilter(status_field, '==', status)).limit(limit)
            )
            snapshots: Iterable[Any] = query.stream()
            created_ats.extend(
                _created_ats_from_page(snapshots, created_at_field=created_at_field, event_type=event_type)
            )
        return created_ats

    query = client.collection_group(collection).limit(limit)
    return _created_ats_from_page(query.stream(), created_at_field=created_at_field, event_type=event_type)


def sample_store_wide_oldest_ready_ages(
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
    finalization_summary: Optional[Mapping[str, Any]] = None,
    page_size: int = _STORE_WIDE_PAGE,
) -> Dict[str, Optional[float]]:
    """Store-wide oldest-ready age per queue. Missing key = sampler failed (leave absent).

    ``None`` values mean the publisher ran and the bounded page had no ready item.
    """
    observed = now if now is not None else datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)

    client = firestore_client
    if client is None:
        try:
            client = get_firestore_client()
        except Exception:
            client = None

    ages: Dict[str, Optional[float]] = {}
    for queue, spec in QUEUE_AGE_SAMPLERS.items():
        try:
            if spec.get('ephemeral'):
                ages[queue] = 0.0
                continue
            if spec.get('summary'):
                if finalization_summary is None:
                    continue
                try:
                    raw_age = finalization_summary.get('oldest_nonterminal_age_seconds')
                    if raw_age is None or isinstance(raw_age, bool):
                        ages[queue] = 0.0
                    else:
                        flt = float(raw_age)
                        ages[queue] = 0.0 if math.isnan(flt) or math.isinf(flt) or flt < 0 else flt
                except (TypeError, ValueError, AttributeError):
                    ages[queue] = 0.0
                continue

            if client is None:
                continue

            created_ats = _sample_status_page(client, spec, page_size=page_size)
            ages[queue] = oldest_ready_age_seconds(created_ats, now=observed)
        except Exception as exc:
            logger.warning("Sampler failed for queue %s: %s", queue, exc)
            continue
    return ages


def publish_all_queue_oldest_ready_ages(
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
    finalization_summary: Optional[Mapping[str, Any]] = None,
    page_size: int = _STORE_WIDE_PAGE,
) -> None:
    """Periodic publisher. Call from the service metrics tick only, never a request path."""
    try:
        from utils.durable_queue_metrics import publish_sampled_queue_oldest_ready_ages
    except ImportError:
        logger.warning("publish_sampled_queue_oldest_ready_ages could not be imported")
        return

    summary = finalization_summary
    if summary is None:
        try:
            from database.conversation_finalization_jobs import get_finalization_job_summary

            summary = get_finalization_job_summary(firestore_client=firestore_client)
        except Exception:
            summary = None

    try:
        ages = sample_store_wide_oldest_ready_ages(
            now=now,
            firestore_client=firestore_client,
            finalization_summary=summary,
            page_size=page_size,
        )
        publish_sampled_queue_oldest_ready_ages(ages)
    except Exception as exc:
        logger.warning("Failed to publish sampled queue oldest ready ages: %s", exc)
