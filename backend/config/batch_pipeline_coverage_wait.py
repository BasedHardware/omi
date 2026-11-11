"""Default-on admission optimization; disabling restores full WAL coverage checks."""

import os


def coverage_wait_memo_enabled() -> bool:
    return os.getenv('SYNC_RECORD_COVERAGE_WAIT_MEMO', 'true').strip().lower() not in {'false', '0', 'off'}
