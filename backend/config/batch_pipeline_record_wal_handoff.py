"""Admission-only kill switch; readers and durable work never consult it."""

import os


def handoff_enabled():
    return os.getenv('RECORD_WAL_HANDOFF_ENABLED', 'true').strip().lower() in {'true', '1', 'on', 'yes'}
