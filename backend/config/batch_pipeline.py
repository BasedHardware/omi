"""Default-off batch admission cohort. Existing lane classification stays upstream."""

from enum import IntEnum
import hashlib
import math
import os

from config.rollout_cohorts import in_rollout_cohort, rollout_cohort_members
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
    if os.getenv('BATCH_PIPELINE_ENABLED', 'false').lower() != 'true':
        return False
    try:
        percent = float(os.getenv('BATCH_PIPELINE_PERCENT', '0'))
    except ValueError:
        return False
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        return False
    return in_rollout_cohort(owner_id, 'batch-pipeline') or in_percent_cohort(owner_id, percent)


def in_percent_cohort(owner_id: str, percent: float) -> bool:
    """Shared unsalted admission bucket; invalid percentages never admit."""
    if not owner_id or not math.isfinite(percent) or not 0 <= percent <= 100:
        return False
    bucket = int.from_bytes(hashlib.sha256(owner_id.encode()).digest()[:4], 'big') / 2**32 * 100
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
    return os.getenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false').lower() == 'true'


def live_record_enabled_for(owner_id: str) -> bool:
    return live_record_admission_enabled() and enabled_for(owner_id)


def record_capture_eligible(owner_id: str, capture: dict) -> bool:
    return bool(
        live_record_enabled_for(owner_id)
        and capture.get('private_cloud_sync_enabled')
        and not capture.get('uses_custom_stt')
        and not capture.get('deleted')
        and not capture.get('discarded')
        and capture.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
        and normalized_stt_language(capture.get('language'))
        in (PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'})
    )


def shared_live_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', 'false').lower() == 'true'


SCHEDULER_SHARDS = 64


def scheduler_control_key(hashed_owner: str) -> str:
    """Pure shard identity shared by scheduling and privacy cleanup."""
    return f'scheduler_{int(hashed_owner[:8], 16) % SCHEDULER_SHARDS:02d}'


def max_worker_attempts() -> int:
    """Bound charged worker failures; malformed configuration keeps the safe default."""
    try:
        value = int(os.getenv('BATCH_PIPELINE_MAX_ATTEMPTS', '5'))
    except ValueError:
        return 5
    return value if 1 <= value <= 20 else 5


def recovery_owners() -> tuple[str, ...]:
    """Recovery is independent of admission; empty allowlist always denies."""
    if os.getenv('BATCH_PIPELINE_RECOVERY_MODE', 'off').strip().lower() != 'on':
        return ()
    return rollout_cohort_members('batch-pipeline-recovery')


def authoritative_labels_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'false').lower() == 'true'


def empty_asr_recovery_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'false').lower() == 'true'


def require_live_target_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_REQUIRE_LIVE_TARGET_ENABLED', 'false').lower() == 'true'


def recover_all_admitted() -> bool:
    # These are already batch-owned obligations; rollback must still drain them.
    return (
        os.getenv('BATCH_PIPELINE_RECOVERY_MODE', 'off').lower() == 'on'
        and os.getenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'false').lower() == 'true'
    )


def recovery_enabled_for(owner_id: str) -> bool:
    return recover_all_admitted() or (
        os.getenv('BATCH_PIPELINE_RECOVERY_MODE', 'off').strip().lower() == 'on'
        and in_rollout_cohort(owner_id, 'batch-pipeline-recovery')
    )


def empty_asr_disposition_enabled() -> bool:
    """Dark strict-VAD disposition; accepted paid intents are never reset."""
    return os.getenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'false').strip().lower() == 'true'


def projection_contention_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', 'false').strip().lower() == 'true'


def speech_empty_multilingual_enabled() -> bool:
    """Dark alternate-provider recovery; one call per durable paid intent."""
    return os.getenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED', 'false').strip().lower() == 'true'


def terminal_empty_disposition_enabled() -> bool:
    """Dark, evidenced terminal empty result; never grants another paid intent."""
    return os.getenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED', 'false').strip().lower() == 'true'


def read_only_metrics_enabled() -> bool:
    """A scrape may stop draining only while the supervised drain is enabled."""
    return (
        os.getenv('BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED', 'false').strip().lower() == 'true'
        and os.getenv('BATCH_PIPELINE_SERVING_ENABLED', 'false').strip().lower() == 'true'
    )


def projection_timing_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_PROJECTION_TIMING_ENABLED', 'false').strip().lower() == 'true'


def worker_silence_disposition_enabled() -> bool:
    """Dark worker-side use of integration's strict local silence evidence."""
    return os.getenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', 'false').strip().lower() == 'true'


def worker_validation_disposition_enabled() -> bool:
    """Ship-on deterministic validation handoff; false restores bounded GPU retries."""
    return os.getenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true').strip().lower() == 'true'


def head_priority_enabled() -> bool:
    """Prefer a queued capture-order head without changing lease/merge authority."""
    return os.getenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'false').strip().lower() == 'true'


def async_projection_enabled() -> bool:
    """Persist in order, then drain durable follow-ups outside the owner claim."""
    return os.getenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'false').strip().lower() == 'true'


def recovery_tasks_enabled() -> bool:
    """Ship-on request-backed paid recovery; false restores inline sweeping."""
    return os.getenv('BATCH_PIPELINE_RECOVERY_TASKS_ENABLED', 'true').strip().lower() == 'true'


def projection_pagination_enabled() -> bool:
    """Ship-on fair discovery; false restores the legacy oldest-page scan."""
    return os.getenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', 'true').strip().lower() == 'true'
