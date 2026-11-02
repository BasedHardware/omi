"""Closed, content-free fleet beacon contract. No customer storage or labels."""

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1] / 'telemetry'
MAX_BYTES = 64 * 1024
MAX_COUNT = 10_000
ABSURD_COUNT = 1_000_000
REASONS = (
    'invalid_schema',
    'unknown_event',
    'unknown_outcome',
    'unknown_histogram',
    'invalid_window',
    'absurd_count',
    'too_large',
    'rate_limited',
    'limiter_unavailable',
    'body_timeout',
)


class FleetValidationError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@lru_cache(maxsize=1)
def registry() -> dict[str, Any]:
    return json.loads((ROOT / 'fleet_registry.json').read_text())


@lru_cache(maxsize=1)
def validator():
    schema = json.loads((ROOT / 'fleet_schema.json').read_text())
    # Event/outcome membership is dispatched above validation in O(n), rather
    # than testing all 74 oneOf alternatives for every counter in a full batch.
    counter = schema['properties']['counters']['items']['oneOf'][0]
    counter['properties'].update(event={'type': 'string'}, outcome={'type': 'string'})
    schema['properties']['counters']['items'] = counter
    return Draft202012Validator(schema)


def max_series() -> int:
    """Includes event _created series and bucket/count counters; excludes target replication."""
    spec = registry()
    axes = len(spec['platforms']) * len(spec['build_channels'])
    events = 2 * sum(map(len, spec['events'].values())) * axes
    histograms = sum(len(item['buckets']) + 1 for item in spec['histograms'].values()) * axes
    # Upload includes unknown platform/channel, four outcomes, total + created.
    uploads = 2 * 4 * (len(spec['platforms']) + 1) * (len(spec['build_channels']) + 1)
    return events + histograms + uploads + 2 * len(REASONS)


def validate_summary(payload: Any, *, now: datetime | None = None) -> tuple[dict[str, Any], bool]:
    spec = registry()
    if not isinstance(payload, dict):
        raise FleetValidationError('invalid_schema')
    counters, histograms = payload.get('counters'), payload.get('histograms')
    if not isinstance(counters, list) or not isinstance(histograms, list):
        raise FleetValidationError('invalid_schema')
    for item in counters[:101]:
        if not isinstance(item, dict) or not isinstance(item.get('event'), str):
            raise FleetValidationError('invalid_schema')
        if item['event'] not in spec['events']:
            raise FleetValidationError('unknown_event')
        if item.get('outcome') not in spec['events'][item['event']]:
            raise FleetValidationError('unknown_outcome')
    for item in histograms[:7]:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            raise FleetValidationError('invalid_schema')
        if item['name'] not in spec['histograms']:
            raise FleetValidationError('unknown_histogram')
    if not validator().is_valid(payload):
        raise FleetValidationError('invalid_schema')
    pattern = r'[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])'
    if not all(re.fullmatch(pattern, payload[key]) for key in ('window_start', 'window_end')):
        raise FleetValidationError('invalid_schema')
    try:
        start = datetime.fromisoformat(payload['window_start'].upper().replace('Z', '+00:00'))
        end = datetime.fromisoformat(payload['window_end'].upper().replace('Z', '+00:00'))
    except ValueError as error:
        raise FleetValidationError('invalid_schema') from error
    now = now or datetime.now(timezone.utc)
    if not 0 < (end - start).total_seconds() <= 3600 or (now - start).total_seconds() > 86400:
        raise FleetValidationError('invalid_window')
    if (end - now).total_seconds() > 300:
        raise FleetValidationError('invalid_window')
    seen = set()
    total = 0
    clamped = False
    for item in counters:
        key = (item['event'], item['outcome'])
        if key in seen or type(item['count']) is not int:
            raise FleetValidationError('invalid_schema')
        seen.add(key)
        total += item['count']
    seen.clear()
    for item in histograms:
        counts = [bucket['count'] for bucket in item['buckets']]
        if item['name'] in seen or counts != sorted(counts) or any(type(n) is not int for n in counts):
            raise FleetValidationError('invalid_schema')
        seen.add(item['name'])
        total += counts[-1]
    if total > ABSURD_COUNT:
        raise FleetValidationError('absurd_count')
    for item in counters:
        clamped |= item['count'] > MAX_COUNT
        item['count'] = min(item['count'], MAX_COUNT)
    for item in histograms:
        for bucket in item['buckets']:
            clamped |= bucket['count'] > MAX_COUNT
            bucket['count'] = min(bucket['count'], MAX_COUNT)
    return payload, clamped
