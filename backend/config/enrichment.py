"""Enrichment queue wiring (plan C3): which handler new ``sr-`` obligations bind to.

``ENRICHMENT_ROUTE`` is the deployment default for contract (c)'s ``enrichment_route`` policy field
until E1's resolver records it per unit. ``sync_handler`` keeps today's ``/v2/sync-jobs/run`` binding;
``enrichment_queue`` binds new rows to ``/v2/enrichment/run`` on the ``enrichment`` queue. A row keeps the
binding it was created with, so switching back never strands in-flight work.

New backfill obligations without a pending first summary use the existing
``SYNC_BACKFILL_TASKS_QUEUE`` when configured, retaining the enrichment handler
and identity. ``ENRICHMENT_BACKFILL_ROUTING_ENABLED=false`` disables that split
for new obligations. ``ENRICHMENT_FRESH_TASKS_QUEUE`` reserves dispatch slots for
pending first summaries only, within the bounded
conversation freshness window. Old work keeps draining on its existing queue.
"""

import os
import math
from datetime import datetime, timezone
from typing import Literal

EnrichmentRoute = Literal['sync_handler', 'enrichment_queue']


def route() -> EnrichmentRoute:
    value = os.getenv('ENRICHMENT_ROUTE', 'sync_handler').strip().lower()
    return 'enrichment_queue' if value == 'enrichment_queue' else 'sync_handler'


def max_age_hours() -> str:
    # Host deployment setting for the historical-enrichment age gate; parsed by utils.enrichment.age_gate.
    return os.getenv('ENRICHMENT_MAX_AGE_HOURS', '72')


def primary_queue() -> str:
    return os.getenv('ENRICHMENT_TASKS_QUEUE', '').strip()


def fresh_queue() -> str:
    return os.getenv('ENRICHMENT_FRESH_TASKS_QUEUE', '').strip()


def fresh_max_age_seconds() -> float:
    try:
        minutes = float(os.getenv('ENRICHMENT_FRESH_PROMOTE_MAX_AGE_MIN', '30'))
        seconds = minutes * 60
        return seconds if math.isfinite(seconds) and seconds >= 0 else 1800
    except ValueError:
        return 1800


def recently_finished(value: object, *, now: float) -> bool:
    """Unknown/future metadata cannot consume the reserved queue; zero disables priority."""
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if isinstance(value, datetime):
            value = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return False
        window = fresh_max_age_seconds()
        return window > 0 and 0 <= now - value <= window
    except (ValueError, OverflowError):
        return False


def dispatch_binding(*, backfill: bool = False, effects_only: bool = False, recent: bool = False) -> dict[str, str]:
    # Share the worker/auth binding; the outbox owns fenced promotion of
    # existing unleased first-summary obligations. Callers admit only pending
    # first summaries through ``recent``.
    queue = primary_queue()
    if backfill and os.getenv('ENRICHMENT_BACKFILL_ROUTING_ENABLED', 'true').strip().lower() != 'false':
        queue = os.getenv('SYNC_BACKFILL_TASKS_QUEUE', '').strip() or queue
    if recent and not backfill and not effects_only:
        queue = fresh_queue() or queue
    handler = os.getenv('ENRICHMENT_TASKS_HANDLER_URL', '').strip()
    return {
        'queue': queue,
        'handler': handler,
        'audience': os.getenv('ENRICHMENT_TASKS_OIDC_AUDIENCE', '').strip() or handler,
        'invoker_sa': os.getenv('ENRICHMENT_TASKS_INVOKER_SA', '').strip()
        or os.getenv('SYNC_TASKS_INVOKER_SA', '').strip(),
    }
