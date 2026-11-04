"""Enrichment queue wiring (plan C3): which handler new ``sr-`` obligations bind to.

``ENRICHMENT_ROUTE`` is the deployment default for contract (c)'s ``enrichment_route`` policy field
until E1's resolver records it per unit. ``sync_handler`` keeps today's ``/v2/sync-jobs/run`` binding;
``enrichment_queue`` binds new rows to ``/v2/enrichment/run`` on the ``enrichment`` queue. A row keeps the
binding it was created with, so switching back never strands in-flight work.

New backfill obligations without a pending first summary use the existing
``SYNC_BACKFILL_TASKS_QUEUE`` when configured, retaining the enrichment handler
and identity. ``ENRICHMENT_BACKFILL_ROUTING_ENABLED=false`` disables that split
for new obligations; active rows and their queued tasks retain their binding.
"""

import os
from typing import Literal

EnrichmentRoute = Literal['sync_handler', 'enrichment_queue']


def route() -> EnrichmentRoute:
    value = os.getenv('ENRICHMENT_ROUTE', 'sync_handler').strip().lower()
    return 'enrichment_queue' if value == 'enrichment_queue' else 'sync_handler'


def dispatch_binding(*, backfill: bool = False) -> dict[str, str]:
    # Share the existing worker/auth binding, but isolate new background work
    # from first-summary dispatch slots. Never change a persisted row's queue.
    queue = os.getenv('ENRICHMENT_TASKS_QUEUE', '').strip()
    if backfill and os.getenv('ENRICHMENT_BACKFILL_ROUTING_ENABLED', 'true').strip().lower() != 'false':
        queue = os.getenv('SYNC_BACKFILL_TASKS_QUEUE', '').strip() or queue
    handler = os.getenv('ENRICHMENT_TASKS_HANDLER_URL', '').strip()
    return {
        'queue': queue,
        'handler': handler,
        'audience': os.getenv('ENRICHMENT_TASKS_OIDC_AUDIENCE', '').strip() or handler,
        'invoker_sa': os.getenv('ENRICHMENT_TASKS_INVOKER_SA', '').strip()
        or os.getenv('SYNC_TASKS_INVOKER_SA', '').strip(),
    }
