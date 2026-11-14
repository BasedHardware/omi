"""CPU projection settlement; GPU telemetry must not import database coordinators."""

from datetime import datetime, timezone
import logging

from database import free_allowance_leases
from utils.executors import free_allowance_executor

logger = logging.getLogger(__name__)


def observe_billed_batch(client, uid, content_id, billing_generation, segment_ids, now):
    """Bound shadow settlement after durable projection; serving never waits on its DB pool."""

    def settle():
        stamp = datetime.fromtimestamp(now, timezone.utc)
        references = [free_allowance_leases.reference(uid, f'batch-unit:{sid}', stamp) for sid in segment_ids]
        for index in range(0, len(references), 32):
            free_allowance_leases.settle_billed(
                references[index : index + 32],
                0,
                now=stamp,
                registered_only=True,
                source='batch',
                batch_content_id=content_id,
                batch_billing_started_at=billing_generation,
                firestore_client=client,
            )

    try:
        free_allowance_executor.submit(settle).result(timeout=2.5)
    except Exception:
        logger.warning('event=free_allowance_lease decision=settlement_unavailable')
