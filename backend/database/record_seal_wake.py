"""Prepare an atomic native-seal wake without cancelling an intake claim.

The retry-marker rule matches Q12-B's 17298c5201d7. A future unmarked clock
may belong to an older intake binary's claim and must survive a seal.
"""

import math
import time

from config.pusher_record import seal_wake_enabled
from config.record_audio import record_identity
from utils.sync.stage import current_stage


def prepare_native_wake(client, tx, uid, cid, row):
    if not seal_wake_enabled() or row.get('status') != 'completed':
        return None
    _, segment = record_identity(uid, cid)
    ref = client.collection(f'batch_pipeline_{current_stage()}_jobs').document(segment)
    job = ref.get(transaction=tx).to_dict() or {}
    if job.get('state') != 'record_pending' or job.get('owner_id') != uid or job.get('conversation_id') != cid:
        return None
    now = time.time()
    enqueued = job.get('enqueued_at')
    available = job.get('available_at', 0)
    retry = job.get('record_intake_retry_at')
    if (
        type(enqueued) in (int, float)
        and math.isfinite(enqueued)
        and 0 <= now - enqueued <= 7200
        and type(available) in (int, float)
        and math.isfinite(available)
        and (available <= now or type(retry) in (int, float) and retry == available)
    ):
        return ref
    return None
