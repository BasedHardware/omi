"""Dark upload producer gate. Compatible readers/drainers never depend on it."""

import math
import os

HOLD_SECONDS = 60.0
MAX_GROUPS = 64
MAX_OWNER_GROUPS = 2
MAX_MEMBERS = 4
MAX_FILES = 20
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_GROUP_BYTES = 8 * 1024 * 1024
MAX_AUDIO_SECONDS = 300.0
DRAIN_PAGE = 8
LEASE_SECONDS = 120.0


def enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', '').strip().lower() == 'true'


def hold_seconds(*, deadline=None, reserve=None, now, batch_pre_unit=False) -> float:
    """No guessed reserve or refreshed stale clock. Batch pre-unit has no Redis job.

    A caller with an applicable processing deadline must supply BOTH that
    original deadline and its qualified processing/queue reserve. Unknown
    budget declines holding. The isolated batch pre-unit seam instead has a
    separate immutable 60s hold bound (see sync_jobs.is_sync_job_stale).
    """
    if batch_pre_unit and deadline is None and reserve is None:
        return HOLD_SECONDS
    if (
        any(
            isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
            for v in (deadline, reserve, now)
        )
        or reserve < 0
    ):
        return 0.0
    return max(0.0, min(HOLD_SECONDS, deadline - reserve - now))
