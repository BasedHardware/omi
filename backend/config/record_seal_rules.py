"""Independent default-on rollback switches for approved seal proof rules."""

import os


def overlap_trim_enabled():
    return os.getenv('RECORD_SEAL_OVERLAP_TRIM_ENABLED', 'true').strip().lower() == 'true'


def upload_failed_repair_enabled():
    return os.getenv('RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED', 'true').strip().lower() == 'true'


def refused_stamp_enabled():
    return os.getenv('RECORD_SEAL_REFUSED_STAMP_ENABLED', 'true').strip().lower() == 'true'
