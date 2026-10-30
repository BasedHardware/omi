"""Cloud Tasks wakes for the provider-STT outbox (contract (a) TaskEdge ``provider-stt``).

Kept outside ``database/outbox*.py`` and ``utils/batch_pipeline/**``, which may not read the environment
(contract (c) invariant 3). The task body is the route's strict shape ``{"kind", "row_id", "wake_token"}``.
"""

import math
import os

ROUTE = '/v2/batch-pipeline/provider-stt/run'


def create_wake(row_id: str, wake_token: str, *, due_at: float) -> None:
    from database.outbox_provider_stt import task_name
    from utils.cloud_tasks import enqueue_named_task

    handler = os.getenv('PROVIDER_STT_TASKS_HANDLER_URL', '').strip().rstrip('/')
    queue = os.getenv('PROVIDER_STT_TASKS_QUEUE', '').strip()
    if not handler or not queue:
        raise RuntimeError('provider-stt task dispatch is not configured')
    audience = os.getenv('PROVIDER_STT_TASKS_OIDC_AUDIENCE', '').strip() or handler
    enqueue_named_task(
        queue,
        handler + ROUTE,
        task_name(row_id, wake_token),
        {'kind': 'provider_stt', 'row_id': row_id, 'wake_token': wake_token},
        audience=audience,
        invoker_sa=os.getenv('SYNC_TASKS_INVOKER_SA', '').strip() or None,
        schedule_at=math.ceil(due_at) if math.isfinite(due_at) else None,
    )
