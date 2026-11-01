"""Controls for the independent in-cluster repair CronJob."""

import json
import os


def enabled():
    return os.getenv('RECORD_SEAL_REPAIR_ENABLED', 'true').strip().lower() == 'true'


def settings():
    workers = int(os.getenv('RECORD_SEAL_REPAIR_WORKERS', '8'))
    row_seconds = int(os.getenv('RECORD_SEAL_REPAIR_ROW_SECONDS', '270'))
    run_seconds = int(os.getenv('RECORD_SEAL_REPAIR_RUN_SECONDS', '1500'))
    mode = os.getenv('RECORD_SEAL_REPAIR_MODE', 'apply')
    if not 1 <= workers <= 16 or not 1 <= row_seconds <= 270 or not 1 <= run_seconds <= 1500:
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
