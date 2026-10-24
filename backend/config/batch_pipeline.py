"""Default-off batch admission cohort. Existing lane classification stays upstream."""

from config.refactor_switches import default_off as rollout_default_off, default_on as rollout_default_on

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


# David's fresh bar (2026-10-20): capture lag at most 10 min at upload.
FRESH_CAPTURE_LAG_SECONDS = 600.0

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


def fresh_gpu_priority_enabled() -> bool:
    """Ship-on: catch-up audio in the 6 h fresh sync lane leases GPU after fresh uploads.

    The owner's FIFO is per priority, so a backlog sharing FRESH queued that
    owner's fresh uploads behind it. ``false`` is the kill switch.
    """
    return rollout_default_on(
        'BATCH_PIPELINE_FRESH_GPU_PRIORITY_ENABLED',
        os.getenv('BATCH_PIPELINE_FRESH_GPU_PRIORITY_ENABLED', 'true').strip().lower() != 'false',
    )


def priority_for(lane: str, recording_age_seconds: float | None) -> Priority:
    if lane == 'fresh':
        if (
            recording_age_seconds is not None
            and math.isfinite(recording_age_seconds)
            and recording_age_seconds > FRESH_CAPTURE_LAG_SECONDS
            and fresh_gpu_priority_enabled()
        ):
            return Priority.RECENT
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
    return rollout_default_off(
        'BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED',
        os.getenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'false').lower() == 'true',
    )


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
    return rollout_default_off(
        'BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED',
        os.getenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'false').strip().lower() == 'true',
    )


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
    return rollout_default_off(
        'BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED',
        os.getenv('BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED', 'false').strip().lower() == 'true',
    ) and rollout_default_off(
        'BATCH_PIPELINE_SERVING_ENABLED', os.getenv('BATCH_PIPELINE_SERVING_ENABLED', 'false').strip().lower() == 'true'
    )


def projection_timing_enabled() -> bool:
    from config.policy import resolve_stage_policy

    return resolve_stage_policy('', 'projection').projection_timing


def worker_silence_disposition_enabled() -> bool:
    """Dark worker-side use of integration's strict local silence evidence."""
    return rollout_default_off(
        'BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED',
        os.getenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', 'false').strip().lower() == 'true',
    )


LONG_SPEECH_HANDOFF_SECONDS = 5.0


def long_speech_handoff_enabled() -> bool:
    """Kill switch (unset is on; only ``false`` disables it).

    A unit whose intake language Parakeet cannot transcribe, with an empty first
    pass and at least LONG_SPEECH_HANDOFF_SECONDS of worker VAD speech, skips the
    padded Parakeet retry and goes straight to quarantine recovery.
    """
    return rollout_default_on(
        'BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED',
        os.getenv('BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED', 'true').strip().lower() != 'false',
    )


def second_multilingual_enabled() -> bool:
    """Kill switch (unset is on; only ``false`` disables it).

    A long-speech handoff unit whose Modulate recovery came back valid-empty gets
    one Deepgram multilingual call inside the same paid recovery intent.
    """
    return rollout_default_on(
        'BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED',
        os.getenv('BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED', 'true').strip().lower() != 'false',
    )


def worker_validation_disposition_enabled() -> bool:
    """Ship-on deterministic validation handoff; false restores bounded GPU retries."""
    return rollout_default_on(
        'BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED',
        os.getenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true').strip().lower() == 'true',
    )


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


RECOVERY_DISPATCH_INTERVAL_DEFAULT = 5.0
RECOVERY_DISPATCH_INTERVAL_MAX = 60.0


def recovery_dispatch_interval_seconds() -> float:
    """Ship-on: serving dispatches quarantine recovery on its own short loop.

    The serving pass (maintenance, projection sweep, then a 20 s sleep) left
    quarantine -> recovery prepared at p50 52 s / p95 97 s in the 5% ramp runs.
    ``off`` or a value <= 0 is the kill switch: dispatch only from the serving
    pass. Malformed or out-of-range values keep the default.
    """
    raw = os.getenv('BATCH_PIPELINE_RECOVERY_DISPATCH_INTERVAL_SECONDS', '').strip().lower()
    if not raw:
        return RECOVERY_DISPATCH_INTERVAL_DEFAULT
    if raw == 'off':
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return RECOVERY_DISPATCH_INTERVAL_DEFAULT
    if value <= 0:
        return 0.0
    return value if 1 <= value <= RECOVERY_DISPATCH_INTERVAL_MAX else RECOVERY_DISPATCH_INTERVAL_DEFAULT


def projection_pagination_enabled() -> bool:
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED')


def owner_chain_projection_enabled() -> bool:
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED')


def recovered_merge_release_enabled() -> bool:
    """Kill switch: the post-recovery owner wake commits the recovered unit (and
    its content's ready siblings) at once past an unready merge head, and the
    unit itself past the catch-up depth hold, so the wake's chain walk can
    project it."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_RECOVERED_MERGE_RELEASE_ENABLED')


def sweep_owner_chain_enabled() -> bool:
    """Kill switch: a sweep that advances an owner's head keeps walking that chain."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED')


def projection_predecessor_replay_enabled() -> bool:
    """Kill switch: blocked page successors wake their owner's missing head."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_PROJECTION_PREDECESSOR_REPLAY_ENABLED')


def projection_pending_page_enabled() -> bool:
    """Kill switch: the assignment page holds only pending rows; finishing pages separately."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED')


def owner_drain_enabled() -> bool:
    """Kill switch: a per-process owner drain replaces the sweep-shared walk budget."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_OWNER_DRAIN_ENABLED')


def projection_index_deferred_enabled() -> bool:
    """Kill switch: walks converge search/people-stats after the chain, once per conversation."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED')


def held_terminal_status_enabled() -> bool:
    """Kill switch: an upload whose failures are all settled held units reads `completed`."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_HELD_TERMINAL_STATUS_ENABLED')


def held_partial_enabled() -> bool:
    """Kill switch: an upload whose unprojected units are all held completes as partial on the ledger."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_HELD_PARTIAL_ENABLED')


def recovery_policy_refresh_enabled() -> bool:
    """Kill switch: a recovery-disabled snapshot with no paid intent re-resolves the setting."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_RECOVERY_POLICY_REFRESH_ENABLED')


PROJECTION_PREFETCH_DEFAULT = 4
PROJECTION_PREFETCH_MAX = 8


def projection_prefetch_depth() -> int:
    """Ship-on read-ahead of an owner chain's immutable inputs; ``0`` is the kill switch.

    Malformed or out-of-range values keep the default rather than silently
    turning the read-ahead off.
    """
    try:
        value = int(os.getenv('BATCH_PIPELINE_PROJECTION_PREFETCH', str(PROJECTION_PREFETCH_DEFAULT)))
    except ValueError:
        return PROJECTION_PREFETCH_DEFAULT
    return value if 0 <= value <= PROJECTION_PREFETCH_MAX else PROJECTION_PREFETCH_DEFAULT


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


def stage_profiling_enabled() -> bool:
    """Dedicated-worker per-stage wall-clock histograms (metrics-only).

    Default on only for the ``dev`` stage; ``prod`` and an unset stage stay off.
    An explicit ``true``/``false`` (also 1/0, on/off, yes/no) overrides the
    stage default so local/offline can opt in; malformed values fall back to
    the stage default rather than failing the worker.
    """
    raw = os.getenv('BATCH_PIPELINE_STAGE_PROFILING_ENABLED', '').strip().lower()
    if raw in {'true', '1', 'on', 'yes'}:
        return True
    if raw in {'false', '0', 'off', 'no'}:
        return False
    return os.getenv('OMI_ENV_STAGE', '').strip().lower() == 'dev'


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


MERGE_HEAD_WAIT_DEFAULT = 60.0
MERGE_HEAD_WAIT_MAX = 3600.0


def merge_head_wait_seconds() -> float:
    """Ship-on bounded ordered-merge head wait (David, 2026-10-20).

    A row ``result_ready`` for this long commits past an earlier pending head,
    which later appends as ``late_capture``. ``off`` or a value <= 0 is the
    kill switch: strict capture order. Malformed or out-of-range values keep
    the default.
    """
    raw = os.getenv('BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS', '').strip().lower()
    if not raw:
        return MERGE_HEAD_WAIT_DEFAULT
    if raw == 'off':
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return MERGE_HEAD_WAIT_DEFAULT
    if value <= 0:
        return 0.0
    return value if value <= MERGE_HEAD_WAIT_MAX else MERGE_HEAD_WAIT_DEFAULT


MERGE_CATCH_UP_DEPTH_DEFAULT = 16
MERGE_CATCH_UP_DEPTH_MAX = 1000


def merge_catch_up_depth() -> int:
    """Ship-on fresh-first merge (David's fresh bar, 2026-10-20).

    Fresh uploads (capture ended at most ``FRESH_CAPTURE_LAG_SECONDS`` before
    admission) commit ahead of the owner's pending catch-up rows, and catch-up
    commits wait while the owner already has this many committed rows awaiting
    projection, so a fresh row never queues behind the owner's whole backlog.
    ``off`` or a value <= 0 is the kill switch: the plain ordered merge.
    Malformed or out-of-range values keep the default.
    """
    raw = os.getenv('BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH', '').strip().lower()
    if not raw:
        return MERGE_CATCH_UP_DEPTH_DEFAULT
    if raw == 'off':
        return 0
    try:
        value = int(raw)
    except ValueError:
        return MERGE_CATCH_UP_DEPTH_DEFAULT
    if value <= 0:
        return 0
    return value if value <= MERGE_CATCH_UP_DEPTH_MAX else MERGE_CATCH_UP_DEPTH_DEFAULT


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
