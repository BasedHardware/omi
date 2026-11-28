"""Independent default-on rollback switches for approved seal proof rules."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import time

from config.refactor_modes import RECORD_TOKEN_LEASE_MODE_ENV, mode, serving_for

# Cover request teardown and final custody metadata after the Cloud Run timeout.
# This floor applies only to the exact, podless custody token, never frame leases.
CUSTODY_REQUEST_MARGIN_SECONDS = 300

# SCA-3748: a fenced custody storage commit never starts more than this long
# after begin, and each bounded commit (client timeout plus retry deadline)
# lands within CUSTODY_WRITE_SECONDS of starting. Their sum stays well under
# half the custody lease, so lease-expiry repair never races a live writer.
CUSTODY_STORAGE_BUDGET_SECONDS = 900
CUSTODY_WRITE_SECONDS = 60
_custody_write_deadline: ContextVar[float | None] = ContextVar('custody_write_deadline', default=None)


class CustodyWriteDeadline(TimeoutError):
    """A fenced custody storage commit would start after its fence's budget."""


def custody_write_deadline():
    """The monotonic commit deadline of the fenced step on this thread, if any."""
    return _custody_write_deadline.get()


def check_custody_write_deadline():
    """Refuse to start a fenced commit after its deadline; None when unfenced."""
    deadline = _custody_write_deadline.get()
    if deadline is not None and time.monotonic() >= deadline:
        raise CustodyWriteDeadline('custody storage budget spent; retain local audio')
    return deadline


def fenced_write_bounds():
    """Check a fenced commit's deadline; bounded GCS call kwargs under a fence, none otherwise."""
    return {} if check_custody_write_deadline() is None else {'timeout': 10, 'retry': None}


@contextmanager
def bound_custody_writes(deadline):
    token = _custody_write_deadline.set(deadline)
    try:
        yield
    finally:
        _custody_write_deadline.reset(token)


@lru_cache(maxsize=1)
def custody_request_timeout_seconds():
    """Packaged deployment config; read lazily, with no credentials or env override."""
    value = json.loads(Path(__file__).with_name('cloud_run_request_timeouts.json').read_text())['backend-sync']
    if type(value) is not int or value <= 0:
        raise ValueError('positive backend-sync request timeout required')
    return value


def custody_token_lease_seconds():
    return max(token_lease_seconds(), custody_request_timeout_seconds() + CUSTODY_REQUEST_MARGIN_SECONDS)


def producer_token_lease_seconds(token):
    if token.get('pod') == '' and token.get('signal_source') == 'custody_append':
        return custody_token_lease_seconds()
    return token_lease_seconds()


def overlap_trim_enabled():
    return os.getenv('RECORD_SEAL_OVERLAP_TRIM_ENABLED', 'true').strip().lower() == 'true'


def upload_failed_repair_enabled():
    return os.getenv('RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED', 'true').strip().lower() == 'true'


def refused_stamp_enabled():
    return os.getenv('RECORD_SEAL_REFUSED_STAMP_ENABLED', 'true').strip().lower() == 'true'


def token_lease_mode():
    return mode(RECORD_TOKEN_LEASE_MODE_ENV, 'off')


def token_lease_serving(uid):
    return serving_for(RECORD_TOKEN_LEASE_MODE_ENV, uid, 'off')


def token_lease_seconds():
    """Conservative seed; retune from shadow gaps at the 10% step."""
    try:
        value = float(os.getenv('RECORD_TOKEN_LEASE_SECONDS', '3600'))
    except ValueError:
        return 3600.0
    return value if math.isfinite(value) and 1800 <= value <= 7200 else 3600.0


def lease_timestamp(value):
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        value = value.timestamp()
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value > 0 else None


def token_lease_clocks(token, *, row=None, job=None):
    """Legacy clocks are computed, never backfilled. Bare legacy True stays fenced.

    The serve-enable epoch is shared by all repair processes (including children
    and new CronJobs). Process start/now would re-anchor stock on every scan.
    A missing epoch deliberately cannot expire stock tokens.
    """
    if (
        not isinstance(token, dict)
        or not isinstance(token.get('pod'), str)
        or not lease_timestamp(token.get('process_started_at'))
    ):
        return None
    if 'lease_expires_at' in token or 'last_signal_at' in token:
        if not token['pod'] and token.get('signal_source') != 'custody_append':
            return None
        signal = lease_timestamp(token.get('last_signal_at'))
        expiry = lease_timestamp(token.get('lease_expires_at'))
        return (signal, expiry) if signal and expiry and expiry >= signal else None
    row = row or {}
    if row.get('status') != 'completed' or not token.get('pod') or not lease_timestamp(token.get('process_started_at')):
        return None
    try:
        deployed = lease_timestamp(float(os.getenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', '0')))
    except ValueError:
        return None
    if deployed is None:
        return None
    # Retry/defer clocks are not activity. The refusal stamp can be cleared
    # on seal and stamped again after reopen, so it is not write-once either.
    # Historical anchors are bounded by enable: later metadata alone must not
    # extend stock beyond enable + lease. Only explicit server signals may.
    signal = min(
        max(deployed, lease_timestamp(row.get('finished_at')) or 0, lease_timestamp(token.get('abandoned_at')) or 0),
        deployed,
    )
    return signal, signal + token_lease_seconds()


def token_lease_lapsed(token, now, *, row=None, job=None):
    clocks = token_lease_clocks(token, row=row, job=job)
    return bool(clocks and now > clocks[1] and now - clocks[0] > token_lease_seconds())
