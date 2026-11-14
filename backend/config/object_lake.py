"""Object-lake admission and codec settings; environment is read at call time."""

import os

from config.policy.batch import cohort_bucket
from config.refactor_switches import default_off as rollout_default_off


def bucket() -> str:
    return os.getenv('BUCKET_OBJECT_LAKE', '').strip()


def kms_key() -> str:
    return os.getenv('OBJECT_LAKE_KMS_KEY', '').strip()


def release() -> str:
    return os.getenv('OBJECT_LAKE_RELEASE', 'v1').strip()


def write_enabled() -> bool:
    return rollout_default_off(
        'OBJECT_LAKE_WRITE_ENABLED', os.getenv('OBJECT_LAKE_WRITE_ENABLED', 'false').lower() == 'true'
    )


def write_percent() -> float:
    try:
        percent = float(os.getenv('OBJECT_LAKE_WRITE_PERCENT', '0'))
    except ValueError:
        return 0.0
    return percent if 0 <= percent <= 100 else 0.0


def read_enabled() -> bool:
    # Resolution remains available while writing is rolled back. C2 owns this gate.
    return os.getenv('OBJECT_LAKE_READ_ENABLED', 'true').lower() == 'true'


def inline_max_bytes() -> int:
    try:
        value = int(os.getenv('OBJECT_LAKE_INLINE_MAX_BYTES', '4096'))
    except ValueError:
        return 4096
    return value if value >= 0 else 4096


def key_cache_ttl_seconds() -> int:
    try:
        value = int(os.getenv('OBJECT_LAKE_KEY_CACHE_TTL_SECONDS', '86400'))
    except ValueError:
        return 86400
    return max(0, value)


_FAKE_KMS_STAGES = frozenset({'local', 'offline'})


# Production stays refused at runtime too, not only in deploy validation, until
# the C4 wipe-coverage gate is green.
_WRITE_STAGES = _FAKE_KMS_STAGES | {'dev'}


def _stage() -> str:
    return os.getenv('OMI_ENV_STAGE', '').strip().lower()


def fake_kms_allowed() -> bool:
    return _stage() in _FAKE_KMS_STAGES


def write_admitted(space_id: str) -> bool:
    return (
        bool(space_id)
        and _stage() in _WRITE_STAGES
        and write_enabled()
        and bool(bucket())
        and bool(release())
        and (bool(kms_key()) or fake_kms_allowed())
        and cohort_bucket(space_id, 'object-lake', bits=64) < write_percent()
    )


def validate_write_settings(stage: str, enabled: object, percent: object) -> list[str]:
    """Deployment gate independent of cohort admission or provisioned bindings."""
    if stage.strip().lower() in _WRITE_STAGES:
        return []
    errors = []
    reason = 'must stay off until the C4 wipe-coverage gate is green'
    if str(enabled).strip().lower() in {'true', '1', 'on', 'yes'}:
        errors.append(f'OBJECT_LAKE_WRITE_ENABLED {reason}')
    try:
        positive = float(str(percent)) > 0
    except ValueError:
        positive = False
    if positive:
        errors.append(f'OBJECT_LAKE_WRITE_PERCENT {reason}')
    return errors


def put_deadline_seconds() -> float:
    """Pointer-success budget only; deletion authority comes from session fencing."""
    return 5.0
