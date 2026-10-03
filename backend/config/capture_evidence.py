"""S1 evidence dark-write admission. Off unless explicitly enabled on this host."""

import os


def capture_evidence_dark_write_enabled() -> bool:
    return os.getenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', '').strip().lower() in {'1', 'true', 'yes', 'on'}
