"""Default-on admission optimizations; disabling each restores the prior path.

Three independent switches, all default on and all read per call:

* ``SYNC_RECORD_COVERAGE_WAIT_MEMO`` - the coverage-wait memo itself.
* ``SYNC_RECORD_WAIT_MEMO_FIRST`` - consult that memo before ``retain_upload``.
  Off restores the pre-change order (retain first, memo after), which still
  memoizes but spends the retained-copy work on every retry.
* ``SYNC_RECORD_DECODE_FAILURE_MEMO`` - repeat a proven deterministic decode
  failure without decoding or staging the same bytes again. The response stays
  the existing 503; only the work is skipped.
"""

import os

# Each name is read literally here, never through a helper: the flag budget and
# the cross-service deploy contract scan the AST for the name at the getenv
# call, and an indirection makes a live kill switch invisible to both.
_OFF = {'false', '0', 'off'}


def _bounded_seconds(value: str | None, minimum: int, default: int) -> int:
    if value is None:
        return default
    try:
        return min(default, max(minimum, int(value)))
    except ValueError:
        return default


def coverage_wait_ttl_seconds() -> int:
    return _bounded_seconds(os.getenv('SYNC_RECORD_COVERAGE_WAIT_TTL_SECONDS'), 30, 6 * 60 * 60)


def coverage_wait_retry_after_seconds() -> int:
    return _bounded_seconds(os.getenv('SYNC_RECORD_COVERAGE_WAIT_RETRY_AFTER_SECONDS'), 30, 30 * 60)


def coverage_wait_memo_enabled() -> bool:
    return os.getenv('SYNC_RECORD_COVERAGE_WAIT_MEMO', 'true').strip().lower() not in _OFF


def record_wait_memo_first_enabled() -> bool:
    return os.getenv('SYNC_RECORD_WAIT_MEMO_FIRST', 'true').strip().lower() not in _OFF


def decode_failure_memo_enabled() -> bool:
    return os.getenv('SYNC_RECORD_DECODE_FAILURE_MEMO', 'true').strip().lower() not in _OFF
