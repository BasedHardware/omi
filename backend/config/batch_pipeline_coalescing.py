"""Dark upload producer gate. Compatible readers/drainers never depend on it."""

import math
import os

from config.batch_pipeline_coalescing_protocol import HOLD_SECONDS


def window_seconds(entitlement_class: str, *, backlog: bool) -> float:
    """Only positively free owners may trade latency for packing. Unset is legacy."""
    if entitlement_class != 'free':
        return HOLD_SECONDS
    name = 'BACKLOG' if backlog else 'FREE'
    try:
        value = float(os.getenv(f'BATCH_PIPELINE_COALESCING_{name}_WINDOW_SECONDS', '60'))
    except ValueError:
        return HOLD_SECONDS
    return min(900.0, value) if math.isfinite(value) and value >= HOLD_SECONDS else HOLD_SECONDS


def enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', '').strip().lower() == 'true'


def hold_seconds(
    *, deadline: float | None = None, reserve: float | None = None, now: float, batch_pre_unit: bool = False
) -> float:
    """No guessed reserve or refreshed stale clock. Batch pre-unit has no Redis job.

    A caller with an applicable processing deadline must supply BOTH that
    original deadline and its qualified processing/queue reserve. Unknown
    budget declines holding. The isolated batch pre-unit seam instead has a
    separate immutable 60s hold bound (see sync_jobs.is_sync_job_stale).
    """
    if batch_pre_unit and deadline is None and reserve is None:
        return HOLD_SECONDS
    if deadline is None or reserve is None:
        return 0.0
    if any(isinstance(v, bool) or not math.isfinite(v) for v in (deadline, reserve, now)) or reserve < 0:
        return 0.0
    return max(0.0, min(HOLD_SECONDS, deadline - reserve - now))
