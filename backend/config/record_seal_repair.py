"""Controls for the independent in-cluster repair CronJob."""

import json
import os

from config import record_partial

# Admission has zero upload grace; use the existing partial proof wait instead.
JOBS_MIN_AGE_SECONDS = record_partial.WAIT_SECONDS
MISSING_CONVERSATION_SECONDS = 7 * record_partial.INVENTORY_IDLE_SECONDS


def jobs_enabled():
    return os.getenv('RECORD_SEAL_REPAIR_JOBS', 'on').strip().lower() != 'off'


def enabled():
    return os.getenv('RECORD_SEAL_REPAIR_ENABLED', 'true').strip().lower() == 'true'


# Rows are I/O-bound subprocesses (~150 s each, 2026-11-05: CPU 0.7 of 4, no throttling, ~70 MB per worker),
# so throughput scales with workers. Prod runs 48; the pod's 8 Gi / 4 CPU limits cover 64.
MAX_WORKERS = 64


def settings():
    workers = int(os.getenv('RECORD_SEAL_REPAIR_WORKERS', '8'))
    row_seconds = int(os.getenv('RECORD_SEAL_REPAIR_ROW_SECONDS', '270'))
    run_seconds = int(os.getenv('RECORD_SEAL_REPAIR_RUN_SECONDS', '1500'))
    mode = os.getenv('RECORD_SEAL_REPAIR_MODE', 'apply')
    if not 1 <= workers <= MAX_WORKERS or not 1 <= row_seconds <= 270 or not 1 <= run_seconds <= 1500:
        raise ValueError('invalid repair limits')
    if mode not in {'apply', 'plan'}:
        raise ValueError('invalid repair mode')
    return workers, row_seconds, run_seconds, mode


def server_flags():
    from utils.batch_pipeline.record_seal_nojob import validate_server_flags

    flags = json.loads(os.environ['RECORD_SEAL_REPAIR_SERVER_FLAGS'])
    validate_server_flags(flags)
    return flags


def cursor_secret() -> bytes:
    """Process bootstrap input; never a batch-stage policy decision."""
    return os.environ['ENCRYPTION_SECRET'].encode()


def require_runtime():
    if os.getenv('FIRESTORE_EMULATOR_HOST') or os.getenv('OMI_ENV_STAGE') != 'prod':
        raise ValueError('production in-cluster runtime required')
