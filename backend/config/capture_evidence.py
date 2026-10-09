"""S1 evidence dark-write admission. Off unless explicitly enabled on this host."""

import os


def capture_evidence_dark_write_enabled() -> bool:
    return os.getenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', '').strip().lower() in {'1', 'true', 'yes', 'on'}


def listen_committed_capture_coverage_enabled() -> bool:
    raw = os.getenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', '').strip().lower()
    return not raw or raw in {'1', 'true', 'yes', 'on', 'enabled'}
