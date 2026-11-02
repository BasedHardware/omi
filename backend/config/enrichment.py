"""Enrichment queue wiring (plan C3): which handler new ``sr-`` obligations bind to.

``ENRICHMENT_ROUTE`` is the deployment default for contract (c)'s ``enrichment_route`` policy field
until E1's resolver records it per unit. ``sync_handler`` keeps today's ``/v2/sync-jobs/run`` binding;
``enrichment_queue`` binds new rows to ``/v2/enrichment/run`` on the ``enrichment`` queue. A row keeps the
binding it was created with, so switching back never strands in-flight work.
"""

import os
from typing import Literal

EnrichmentRoute = Literal['sync_handler', 'enrichment_queue']


def route() -> EnrichmentRoute:
    value = os.getenv('ENRICHMENT_ROUTE', 'sync_handler').strip().lower()
    return 'enrichment_queue' if value == 'enrichment_queue' else 'sync_handler'


def dispatch_binding() -> dict[str, str]:
    handler = os.getenv('ENRICHMENT_TASKS_HANDLER_URL', '').strip()
    return {
        'queue': os.getenv('ENRICHMENT_TASKS_QUEUE', '').strip(),
        'handler': handler,
        'audience': os.getenv('ENRICHMENT_TASKS_OIDC_AUDIENCE', '').strip() or handler,
        'invoker_sa': os.getenv('ENRICHMENT_TASKS_INVOKER_SA', '').strip()
        or os.getenv('SYNC_TASKS_INVOKER_SA', '').strip(),
    }
