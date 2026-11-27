"""Dark by default; Release qualifies the retained source fence independently."""

import hashlib
import os

from config.batch_pipeline_record_wal_handoff import handoff_enabled
from config.record_wal_sample import ATTEMPT_SECONDS, SLOT_SECONDS

ARCHIVE_BUCKET = 'omi-private-cloud-sync'
MAX_JOBS = 4
SOURCE_FIELD = 'wal_duplicate_source_v1'
RECEIPT_FIELD = 'wal_duplicate_settlement_v1'
# Shadow-only: 4 h of 30 s slots keeps the 480-proof cap; the sampler's slots are separate.
SHADOW_SLOT_SECONDS = 30
SHADOW_WINDOW_SECONDS = 14_400
# The 1-in-1000 content filter was sized for 180 s slots; scale it so each slot sees as many candidates.
DESIGN_CONTENT_MODULUS = 1000
SHADOW_CONTENT_MODULUS = round(DESIGN_CONTENT_MODULUS * SHADOW_SLOT_SECONDS / SLOT_SECONDS)


def mode(uid: str, now: float) -> tuple[str, int | None]:
    if os.getenv('K_SERVICE') != 'backend-sync':
        return 'off', None
    fenced = os.getenv('RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED') == 'true'
    # Admits the read-only shadow only; settlement below still requires the fence.
    shadow_pre_fence = os.getenv('RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE') == 'true'
    if not (fenced or shadow_pre_fence) or handoff_enabled():
        return 'off', None
    try:
        percent = int(os.getenv('RECORD_WAL_DUPLICATE_PERCENT', '0'))
        start = int(os.getenv('RECORD_WAL_DUPLICATE_SHADOW_EPOCH', '0'))
    except ValueError:
        return 'off', None
    if start:
        if (
            percent
            or start < 0
            or start % SHADOW_SLOT_SECONDS
            or not start <= now < start + SHADOW_WINDOW_SECONDS - ATTEMPT_SECONDS
        ):
            return 'off', None
        return 'shadow', int(now) // SHADOW_SLOT_SECONDS
    if not fenced or percent not in {1, 10, 50, 100}:
        return 'off', None
    bucket = int.from_bytes(hashlib.sha256(uid.encode()).digest()[:8], 'big') % 100
    return ('settle', None) if bucket < percent else ('off', None)


# These persisted fields remain authoritative when admission is disabled.
SETTLED_FIELD = 'wal_duplicate_settled_v1'
MERGE_PLAN_FIELD = 'wal_duplicate_merge_plan_v1'
MERGE_TARGET_FIELD = 'wal_duplicate_merge_target_v1'
RETAINED_DONORS_FIELD = 'wal_duplicate_retained_donors_v1'


def has_retained_custody(row) -> bool:
    """Unsupported lineage writers must defer even when settlement is disabled."""
    return bool(row and (row.get(SETTLED_FIELD) or row.get(RETAINED_DONORS_FIELD) or row.get(MERGE_TARGET_FIELD)))
