"""Default-on admission optimizations; disabling each restores the prior path.

Four independent switches, all default on and all read per call:

* ``SYNC_RECORD_COVERAGE_WAIT_MEMO`` - the coverage-wait memo itself.
* ``SYNC_RECORD_WAIT_MEMO_FIRST`` - consult that memo before ``retain_upload``.
  Off restores the pre-change order (retain first, memo after), which still
  memoizes but spends the retained-copy work on every retry.
* ``SYNC_RECORD_DECODE_FAILURE_MEMO`` - repeat a proven deterministic decode
  failure without decoding or staging the same bytes again. The response stays
  the existing 503; only the work is skipped.
* ``SYNC_RECORD_COVERAGE_TERMINAL`` - once a registered record is closed and
  sealed and has not changed for ``COVERAGE_FINAL_AFTER_SECONDS``, an unproven
  WAL gets the terminal keep-local refusal instead of the retryable 503.
  Off restores the 503 for every unproven WAL.
"""

import os

# Each name is read literally here, never through a helper: the flag budget and
# the cross-service deploy contract scan the AST for the name at the getenv
# call, and an indirection makes a live kill switch invisible to both.
_OFF = {'false', '0', 'off'}

# A sealed record whose seal and finish are both this old no longer changes its
# units on any normal path (pusher flushes, seal, seal repair), so a negative
# coverage check against it is final. A later reseal restarts the clock.
COVERAGE_FINAL_AFTER_SECONDS = 6 * 3600


def coverage_wait_memo_enabled() -> bool:
    return os.getenv('SYNC_RECORD_COVERAGE_WAIT_MEMO', 'true').strip().lower() not in _OFF


def record_wait_memo_first_enabled() -> bool:
    return os.getenv('SYNC_RECORD_WAIT_MEMO_FIRST', 'true').strip().lower() not in _OFF


def decode_failure_memo_enabled() -> bool:
    return os.getenv('SYNC_RECORD_DECODE_FAILURE_MEMO', 'true').strip().lower() not in _OFF


def coverage_terminal_enabled() -> bool:
    return os.getenv('SYNC_RECORD_COVERAGE_TERMINAL', 'true').strip().lower() not in _OFF
