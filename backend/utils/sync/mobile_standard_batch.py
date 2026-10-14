"""Admission for the mobile Standard batch lane; every switch defaults off."""

import hashlib
import os


def mobile_standard_batch_enabled(uid: str) -> bool:
    if os.getenv('MOBILE_STANDARD_BATCH_ENABLED', '').lower() != 'true' or not uid:
        return False
    allowlist = {value.strip() for value in os.getenv('MOBILE_STANDARD_BATCH_UIDS', '').split(',') if value.strip()}
    if uid in allowlist:
        return True
    try:
        percent = int(os.getenv('MOBILE_STANDARD_BATCH_PERCENT', '0'))
    except ValueError:
        return False
    if not 0 <= percent <= 100:
        return False
    bucket = int(hashlib.sha256(f'mobile-standard-batch:{uid}'.encode()).hexdigest()[:8], 16) % 10000
    return bucket < percent * 100
