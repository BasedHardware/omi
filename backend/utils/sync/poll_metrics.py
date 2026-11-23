"""Low-cardinality, process-local telemetry for the sync-poll cohort rollout."""

from __future__ import annotations

import hashlib
import math
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from functools import partial
from typing import Any

from config.repeat_work import poll_backoff_cohort
from utils.metrics import (
    OMI_SYNC_JOB_COMPLETION_TO_FIRST_TERMINAL_READ_SECONDS,
    OMI_SYNC_JOB_POLL_ACTIVE_UPLOADERS,
    OMI_SYNC_JOB_POLL_COHORT_REQUESTS_TOTAL,
)

ACTIVE_UID_WINDOW_SECONDS = 5 * 60
MAX_ACTIVE_UIDS_PER_PROCESS = 50_000
TERMINAL_READ_DEDUPE_SECONDS = 24 * 60 * 60
MAX_TERMINAL_JOBS_PER_PROCESS = 50_000
_HASH_SALT = os.urandom(32)
_LOCK = threading.Lock()
_ACTIVE_UIDS: OrderedDict[bytes, tuple[float, str]] = OrderedDict()
_ACTIVE_UID_COUNTS = {'in': 0, 'out': 0}
_TERMINAL_JOBS: OrderedDict[bytes, float] = OrderedDict()


def record_sync_job_poll_request(uid: str | None) -> str:
    """Count one status request and return its low-cardinality cohort label."""
    cohort = poll_backoff_cohort(uid)
    OMI_SYNC_JOB_POLL_COHORT_REQUESTS_TOTAL.labels(cohort=cohort).inc()
    return cohort


def record_active_sync_uploader(uid: str | None, status: dict[str, Any]) -> None:
    """Record a returned nonterminal job in the bounded active-uploader window."""
    is_active = bool(uid) and status.get('status') not in {'completed', 'partial_failure', 'failed'}
    with _LOCK:
        now = time.monotonic()
        _prune_active_uids(now)
        if is_active and uid:
            cohort = poll_backoff_cohort(uid)
            uid_digest = hashlib.sha256(_HASH_SALT + uid.encode('utf-8')).digest()
            prior = _ACTIVE_UIDS.pop(uid_digest, None)
            if prior is None:
                _ACTIVE_UID_COUNTS[cohort] += 1
            elif prior[1] != cohort:
                _ACTIVE_UID_COUNTS[prior[1]] -= 1
                _ACTIVE_UID_COUNTS[cohort] += 1
            _ACTIVE_UIDS[uid_digest] = (now, cohort)

        while len(_ACTIVE_UIDS) > MAX_ACTIVE_UIDS_PER_PROCESS:
            _, (_, evicted_cohort) = _ACTIVE_UIDS.popitem(last=False)
            _ACTIVE_UID_COUNTS[evicted_cohort] -= 1


def _prune_active_uids(now: float) -> None:
    while _ACTIVE_UIDS:
        _, (seen_at, cohort) = next(iter(_ACTIVE_UIDS.items()))
        if now - seen_at <= ACTIVE_UID_WINDOW_SECONDS:
            break
        _ACTIVE_UIDS.popitem(last=False)
        _ACTIVE_UID_COUNTS[cohort] -= 1


def _active_uploader_count(cohort: str) -> int:
    with _LOCK:
        _prune_active_uids(time.monotonic())
        return _ACTIVE_UID_COUNTS[cohort]


for _cohort in _ACTIVE_UID_COUNTS:
    OMI_SYNC_JOB_POLL_ACTIVE_UPLOADERS.labels(cohort=_cohort).set_function(partial(_active_uploader_count, _cohort))


def record_first_terminal_read(uid: str | None, status: dict[str, Any]) -> None:
    """Observe completion visibility once per job per process, without storing IDs."""
    if status.get('status') not in {'completed', 'partial_failure', 'failed'}:
        return
    job_id = status.get('job_id')
    completed_at = _epoch_seconds(status.get('completed_at'))
    if not isinstance(job_id, str) or not job_id or completed_at is None:
        return

    delay = time.time() - completed_at
    if not math.isfinite(delay) or delay < 0:
        return

    now = time.monotonic()
    job_digest = hashlib.sha256(_HASH_SALT + job_id.encode('utf-8')).digest()
    cohort = poll_backoff_cohort(uid)
    with _LOCK:
        while _TERMINAL_JOBS:
            _, seen_at = next(iter(_TERMINAL_JOBS.items()))
            if now - seen_at <= TERMINAL_READ_DEDUPE_SECONDS:
                break
            _TERMINAL_JOBS.popitem(last=False)
        if job_digest in _TERMINAL_JOBS:
            return
        _TERMINAL_JOBS[job_digest] = now
        while len(_TERMINAL_JOBS) > MAX_TERMINAL_JOBS_PER_PROCESS:
            _TERMINAL_JOBS.popitem(last=False)

    OMI_SYNC_JOB_COMPLETION_TO_FIRST_TERMINAL_READ_SECONDS.labels(cohort=cohort).observe(delay)


def _epoch_seconds(value: Any) -> float | None:
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return aware.timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return None
            aware = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            return aware.timestamp()
    return None
