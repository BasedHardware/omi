"""Store-wide oldest-ready age samples. Kept off ``durable_queue.py`` so isolated
tests can load policy/redrive without the Firestore SDK.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from utils.durable_queue_policy import oldest_ready_age_seconds

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


def _created_ats_from_page(
    snapshots: Iterable[Any],
    *,
    created_at_field: str,
    event_type: Optional[str] = None,
) -> List[datetime]:
    created_ats: List[datetime] = []
    for snapshot in snapshots:
        payload = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else snapshot
        if not isinstance(payload, dict):
            continue
        if event_type is not None and payload.get('event_type') != event_type:
            continue
        created_at = payload.get(created_at_field)
        if isinstance(created_at, datetime):
            created_ats.append(created_at)
    return created_ats


def _sample_status_page(client: Any, spec: Mapping[str, Any]) -> List[datetime]:
    collection = str(spec['collection'])
    created_at_field = str(spec['created_at_field'])
    event_type = spec.get('event_type')
    status_field = spec.get('status_field')
    ready_statuses: tuple[Any, ...] = tuple(spec.get('ready_statuses') or ())
    created_ats: List[datetime] = []
    if status_field and ready_statuses:
        for status in ready_statuses:
            query = (
                client.collection_group(collection)
                .where(filter=FieldFilter(status_field, '==', status))
                .limit(_STORE_WIDE_PAGE)
            )
            snapshots: Iterable[Any] = query.stream()
            created_ats.extend(
                _created_ats_from_page(snapshots, created_at_field=created_at_field, event_type=event_type)
            )
        return created_ats
    query = client.collection_group(collection).limit(_STORE_WIDE_PAGE)
    return _created_ats_from_page(query.stream(), created_at_field=created_at_field, event_type=event_type)


def sample_store_wide_oldest_ready_ages(
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
    finalization_summary: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Optional[float]]:
    """Store-wide oldest-ready age per queue. Missing key = sampler failed (leave absent).

    ``None`` values mean the publisher ran and the bounded page had no ready item.
    """
    observed = now or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ages: Dict[str, Optional[float]] = {}
    for queue, spec in QUEUE_AGE_SAMPLERS.items():
        try:
            if spec.get('ephemeral'):
                ages[queue] = 0.0
                continue
            if spec.get('summary'):
                if finalization_summary is None:
                    continue
                ages[queue] = float(finalization_summary.get('oldest_nonterminal_age_seconds') or 0.0)
                continue
            created_ats = _sample_status_page(client, spec)
            ages[queue] = oldest_ready_age_seconds(created_ats, now=observed)
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
    from utils.durable_queue_metrics import publish_sampled_queue_oldest_ready_ages

    summary = finalization_summary
    if summary is None:
        try:
            from database.conversation_finalization_jobs import get_finalization_job_summary

            summary = get_finalization_job_summary(firestore_client=firestore_client)
        except Exception:
            summary = None
    publish_sampled_queue_oldest_ready_ages(
        sample_store_wide_oldest_ready_ages(
            now=now,
            firestore_client=firestore_client,
            finalization_summary=summary,
        )
    )
