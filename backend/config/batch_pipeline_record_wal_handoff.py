"""Readers-first admission switch and conservative durable storage budgets."""

import os


def handoff_enabled():
    return os.getenv('RECORD_WAL_HANDOFF_ENABLED', 'false').strip().lower() in {'true', '1', 'on', 'yes'}


def pending_limits():
    """Zero closes admission; malformed limits fail closed before any object write."""
    return {
        'owner_bytes': max(0, int(os.getenv('RECORD_WAL_PENDING_OWNER_BYTES', '268435456'))),
        'owner_files': max(0, int(os.getenv('RECORD_WAL_PENDING_OWNER_FILES', '200'))),
        'global_bytes': max(0, int(os.getenv('RECORD_WAL_PENDING_GLOBAL_BYTES', '4294967296'))),
        'global_files': max(0, int(os.getenv('RECORD_WAL_PENDING_GLOBAL_FILES', '10000'))),
    }
