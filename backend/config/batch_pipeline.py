"""Default-off batch admission cohort. Existing lane classification stays upstream."""

from enum import IntEnum
import math
import os

from config.rollout_cohorts import rollout_cohort_members
from typing import Callable, TypeVar
from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL, normalized_stt_language


class Priority(IntEnum):
    FRESH = 0
    RECENT = 1
    DEEP = 2


T = TypeVar('T')


class RecordOwnerContention(RuntimeError):
    """A loaded conversation revision lost a route-only compare-and-set."""


def enabled_for(owner_id: str) -> bool:
    from config.policy import resolve_batch_policy

    return resolve_batch_policy(owner_id).batch_enabled


def in_percent_cohort(owner_id: str, percent: float) -> bool:
    """Shared unsalted admission bucket; invalid percentages never admit."""
    if not owner_id or not math.isfinite(percent) or not 0 <= percent <= 100:
        return False
    from config.policy import cohort_bucket

    bucket = cohort_bucket(owner_id, '')
    return bucket < percent


def priority_for(lane: str, recording_age_seconds: float | None) -> Priority:
    if lane == 'fresh':
        return Priority.FRESH
    if lane != 'backfill':
        raise ValueError('unclassified sync lane')
    if (
        recording_age_seconds is not None
        and math.isfinite(recording_age_seconds)
        and 0 <= recording_age_seconds <= 604800
    ):
        return Priority.RECENT
    return Priority.DEEP


def admit_or_legacy(owner_id: str, admit: Callable[..., T], legacy: Callable[..., T], *args, **kwargs) -> T:
    """Explicit integration seam; disabled path does not evaluate admission/store."""
    return (admit if enabled_for(owner_id) else legacy)(*args, **kwargs)


def live_record_admission_enabled() -> bool:
    from config.policy import resolve_batch_policy

    return resolve_batch_policy('').live_admission_enabled


def live_record_enabled_for(owner_id: str) -> bool:
    from config.policy import resolve_batch_policy

    return resolve_batch_policy(owner_id).live_record_enabled


def record_capture_eligible(owner_id: str, capture: dict, *, policy=None) -> bool:
    from config.policy import resolve_batch_policy

    policy = policy or resolve_batch_policy(owner_id)
    return bool(
        policy.live_record_enabled
        and capture.get('private_cloud_sync_enabled')
        and not capture.get('uses_custom_stt')
        and not capture.get('deleted')
        and not capture.get('discarded')
        and capture.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
        and normalized_stt_language(capture.get('language'))
        in (PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'})
    )


def shared_live_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'scheduler').shared_live


SCHEDULER_SHARDS = 64


def scheduler_control_key(hashed_owner: str) -> str:
    """Pure shard identity shared by scheduling and privacy cleanup."""
    return f'scheduler_{int(hashed_owner[:8], 16) % SCHEDULER_SHARDS:02d}'


def max_worker_attempts() -> int:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'scheduler').max_attempts


def recovery_owners() -> tuple[str, ...]:
    from config.policy import resolve_stage_policy

    if resolve_stage_policy('', 'recovery').recovery_mode != 'on':
        return ()
    return rollout_cohort_members('batch-pipeline-recovery')


def authoritative_labels_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'projection').authoritative_labels


def empty_asr_recovery_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'false').lower() == 'true'


def require_live_target_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'projection').require_live_target


def recover_all_admitted() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'recovery').recovery_all_admitted


def recovery_enabled_for(owner_id: str) -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy(owner_id, 'recovery').recovery_enabled


def empty_asr_disposition_enabled() -> bool:
    """Dark strict-VAD disposition; accepted paid intents are never reset."""
    return os.getenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'false').strip().lower() == 'true'


def projection_contention_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'projection').projection_contention


def speech_empty_multilingual_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'recovery').speech_empty_multilingual


def terminal_empty_disposition_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'recovery').terminal_empty_disposition


def read_only_metrics_enabled() -> bool:
    """A scrape may stop draining only while the supervised drain is enabled."""
    return (
        os.getenv('BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED', 'false').strip().lower() == 'true'
        and os.getenv('BATCH_PIPELINE_SERVING_ENABLED', 'false').strip().lower() == 'true'
    )


def projection_timing_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'projection').projection_timing


def worker_silence_disposition_enabled() -> bool:
    """Dark worker-side use of integration's strict local silence evidence."""
    return os.getenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', 'false').strip().lower() == 'true'


def worker_validation_disposition_enabled() -> bool:
    """Ship-on deterministic validation handoff; false restores bounded GPU retries."""
    return os.getenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true').strip().lower() == 'true'


def head_priority_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'scheduler').head_priority


def async_projection_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'projection').async_projection


def recovery_tasks_enabled() -> bool:
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_RECOVERY_TASKS_ENABLED')


def recovery_dispatch_batch_size() -> int:
    """Bound each serving pass; 1 restores the former all-admitted dispatch rate."""
    try:
        value = int(os.getenv('BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE', '16'))
    except ValueError:
        return 16
    return value if 1 <= value <= 64 else 16


def projection_pagination_enabled() -> bool:
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED')


def owner_chain_projection_enabled() -> bool:
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED')


WORKER_PIPELINE_DEPTH_DEFAULT = 2
WORKER_PIPELINE_DEPTH_MAX = 4


def worker_pipeline_depth() -> int:
    """Ship-on pump flights per GPU process; ``1`` restores the serial pump.

    Only claim/admission and publication overlap: the GPU chain itself stays
    exclusive, so device and host memory remain one flight. Malformed values
    keep the default rather than silently serializing.
    """
    try:
        value = int(os.getenv('BATCH_PIPELINE_WORKER_PIPELINE_DEPTH', str(WORKER_PIPELINE_DEPTH_DEFAULT)))
    except ValueError:
        return WORKER_PIPELINE_DEPTH_DEFAULT
    return value if 1 <= value <= WORKER_PIPELINE_DEPTH_MAX else WORKER_PIPELINE_DEPTH_DEFAULT


WORKER_IO_CONCURRENCY_DEFAULT = 3
WORKER_IO_CONCURRENCY_MAX = 8


def worker_io_concurrency() -> int:
    """Bounded artifact fetch/decode and encrypted persistence inside one GPU flight.

    1 restores the fully serial chain. Malformed or out-of-range values keep the
    conservative default; GPU work and the chain lock are unaffected either way.
    """
    try:
        value = int(os.getenv('BATCH_PIPELINE_WORKER_IO_CONCURRENCY', str(WORKER_IO_CONCURRENCY_DEFAULT)))
    except ValueError:
        return WORKER_IO_CONCURRENCY_DEFAULT
    return value if 1 <= value <= WORKER_IO_CONCURRENCY_MAX else WORKER_IO_CONCURRENCY_DEFAULT


DEFAULT_PUBLISH_CONCURRENCY = 4
MAX_PUBLISH_CONCURRENCY = 16


def publish_concurrency() -> int:
    """Ship-on bounded post-flight publication; 1 is the kill switch.

    Bounds concurrent fenced transitions and cross-owner ordered drains after
    one GPU flight. ``1`` restores serial transitions with one drain after each
    accepted transition. Malformed values fall back to that serial path.
    """
    raw = os.getenv('BATCH_PIPELINE_PUBLISH_CONCURRENCY', str(DEFAULT_PUBLISH_CONCURRENCY)).strip()
    try:
        value = int(raw)
    except ValueError:
        return 1
    return value if 1 <= value <= MAX_PUBLISH_CONCURRENCY else 1


RECOVERY_WAKE_LEASE_DEFAULT = 600
RECOVERY_WAKE_LEASE_MAX = 3600


def recovery_wake_lease_seconds() -> int:
    """Ship-on: one outstanding recovery delivery task per prepared intent.

    The lease bounds how long an undelivered wake is trusted before the sweep
    repairs it with a new one. ``0`` is the kill switch: the legacy 120s
    time-bucketed wake on every sweep. Malformed or out-of-range values keep the
    default.
    """
    try:
        value = int(os.getenv('BATCH_PIPELINE_RECOVERY_WAKE_LEASE_SECONDS', str(RECOVERY_WAKE_LEASE_DEFAULT)))
    except ValueError:
        return RECOVERY_WAKE_LEASE_DEFAULT
    if value == 0:
        return 0
    return value if 120 <= value <= RECOVERY_WAKE_LEASE_MAX else RECOVERY_WAKE_LEASE_DEFAULT
