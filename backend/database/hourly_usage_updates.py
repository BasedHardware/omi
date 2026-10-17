"""Shared hourly usage increments, plan attribution, and shadow metadata."""

from datetime import datetime, timezone
from typing import Any, Dict, Mapping
from google.cloud import firestore
from database.llm_usage import nest_usage_fields
from database.usage_units import hourly_shadow


def prepare_hourly_usage_updates(
    date: datetime,
    updates: Dict[str, Any],
    plan_key: str | None,
    *,
    cost_usd: float | None = None,
    cost_status: str = 'missing',
    cost_exclusion: str | None = None,
    usage_metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    doc_id = f'{date.year}-{date.month:02d}-{date.day:02d}-{date.hour:02d}'
    update_doc: Dict[str, Any] = {
        'last_updated': datetime.now(timezone.utc),
        'year': date.year,
        'month': date.month,
        'day': date.day,
        'hour': date.hour,
        'id': doc_id,
    }
    for key, value in updates.items():
        if (
            key
            in {'transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds'}
            and value > 0
        ):
            update_doc[key] = firestore.Increment(value)
    has_increments = any(
        key in {'transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds'}
        for key in update_doc
    )
    if not has_increments:
        return {}
    plan_key = plan_key or '_unattributed'
    plan_prefix = f'plan_usage.{plan_key}'
    for key, value in updates.items():
        if (
            key
            in {'transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds'}
            and value > 0
        ):
            update_doc[f'{plan_prefix}.{key}'] = firestore.Increment(value)
    if cost_usd is not None:
        update_doc[f'{plan_prefix}.cost_usd'] = firestore.Increment(cost_usd)
    normalized_status = cost_status if cost_status in {'complete', 'partial', 'missing', 'excluded'} else 'missing'
    effective_exclusion = cost_exclusion or (
        'provider_cost_not_recorded' if normalized_status in {'missing', 'partial'} else None
    )
    update_doc[f'{plan_prefix}._metadata.cost_status_counts.{normalized_status}'] = firestore.Increment(1)
    update_doc[f'{plan_prefix}._metadata.last_cost_status'] = normalized_status
    if effective_exclusion:
        safe_exclusion = effective_exclusion.replace('.', '_').replace('/', '_')
        update_doc[f'{plan_prefix}._metadata.cost_exclusions.{safe_exclusion}'] = firestore.Increment(1)
    update_doc.update(hourly_shadow(updates, usage_metadata))
    return nest_usage_fields(update_doc)
