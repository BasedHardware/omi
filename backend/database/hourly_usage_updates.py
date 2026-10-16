"""Shared hourly usage increments, plan attribution, and shadow metadata."""

from datetime import datetime, timezone
import math
from typing import Any, Dict, Mapping
from google.cloud import firestore
from database.llm_usage import nest_usage_fields
from database.usage_units import hourly_shadow

METRIC_KEYS = {'transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds'}
SPECIAL_FIELD_CHARS = ('.', '/', '~', '*', '[', ']', '`')


def _sanitize_field_segment(name: str) -> str:
    for char in SPECIAL_FIELD_CHARS:
        name = name.replace(char, '_')
    return name


def _is_valid_positive_increment(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value) and value > 0
    return False


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
    if date.tzinfo is not None:
        date = date.astimezone(timezone.utc)
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
        if key in METRIC_KEYS and _is_valid_positive_increment(value):
            update_doc[key] = firestore.Increment(value)
    has_increments = any(key in METRIC_KEYS for key in update_doc)
    if not has_increments:
        return {}
    stripped_plan = plan_key.strip() if plan_key else ''
    safe_plan = _sanitize_field_segment(stripped_plan) if stripped_plan else '_unattributed'
    plan_prefix = f'plan_usage.{safe_plan}'
    for key, value in updates.items():
        if key in METRIC_KEYS and _is_valid_positive_increment(value):
            update_doc[f'{plan_prefix}.{key}'] = firestore.Increment(value)
    if cost_usd is not None and not isinstance(cost_usd, bool):
        try:
            num_cost = float(cost_usd)
            if math.isfinite(num_cost) and num_cost >= 0:
                update_doc[f'{plan_prefix}.cost_usd'] = firestore.Increment(num_cost)
        except (TypeError, ValueError):
            pass
    normalized_status = cost_status if cost_status in {'complete', 'partial', 'missing', 'excluded'} else 'missing'
    effective_exclusion = cost_exclusion or (
        'provider_cost_not_recorded' if normalized_status in {'missing', 'partial'} else None
    )
    update_doc[f'{plan_prefix}._metadata.cost_status_counts.{normalized_status}'] = firestore.Increment(1)
    update_doc[f'{plan_prefix}._metadata.last_cost_status'] = normalized_status
    if effective_exclusion:
        safe_exclusion = _sanitize_field_segment(effective_exclusion)
        update_doc[f'{plan_prefix}._metadata.cost_exclusions.{safe_exclusion}'] = firestore.Increment(1)
    update_doc.update(hourly_shadow(updates, usage_metadata))
    return nest_usage_fields(update_doc)
