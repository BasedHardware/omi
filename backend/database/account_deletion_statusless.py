"""Pure decision for re-driving status-less account-deletion markers. No I/O, no clients.

A marker whose ``wipe_status`` is absent or blank is invisible to the reconciler
(equality queries) and to the task claim (``not_actionable``). The only transition
given to such a marker is ``pending``, and it reuses an existing ``wipe_job_id``.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any


def is_statusless_marker(data: Mapping[str, Any] | None) -> bool:
    """True only for an existing marker with no usable ``wipe_status``."""
    if data is None:
        return False
    raw_status = data.get('wipe_status')
    return not (isinstance(raw_status, str) and raw_status.strip())


def requeue_fields(data: Mapping[str, Any] | None, generated_job_id: str, now: datetime) -> dict[str, Any] | None:
    """Fields to write when re-driving this marker, or ``None`` when it must not change."""
    if not is_statusless_marker(data):
        return None
    job_id = data.get('wipe_job_id') if data else None
    if not isinstance(job_id, str) or not job_id:
        job_id = generated_job_id
    return {'wipe_status': 'pending', 'wipe_queued_at': now, 'wipe_job_id': job_id}
