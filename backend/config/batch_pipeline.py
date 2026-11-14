"""Default-off batch admission cohort. Existing lane classification stays upstream."""

from config.policy import kill_switch
from config.refactor_switches import default_off as rollout_default_off, default_on as rollout_default_on

from enum import IntEnum
import hashlib
import logging
import math
import os
import re
import secrets
import threading

from config.rollout_cohorts import rollout_cohort_members
from typing import Callable, TypeVar
from config.stt_provider_policy import (
    MODULATE_SUPPORTED_LANGUAGES,
    PARAKEET_MODEL_BY_SURFACE,
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL,
    STTServingSurface,
    normalized_stt_language,
)


class Priority(IntEnum):
    FRESH = 0
    RECENT = 1
    DEEP = 2


# David's fresh bar (2026-10-20): capture lag at most 10 min at upload.
FRESH_CAPTURE_LAG_SECONDS = 600.0

# Terminal exclusion keeps future nonterminal strings visible; the census gates missing/null state.
MERGE_POLL_TERMINAL_STATES = tuple(
    'committed dead quarantined privacy_blocked partial_retired provider_superseded'.split()
)


def held_poll_skip_enabled() -> bool:
    from config.refactor_modes import default_off

    return default_off('BATCH_HELD_POLL_SKIP_ENABLED')


# A full grace window is also given to pre-field rows on first observation.
HELD_DEAD_LETTER_SECONDS = 7 * 86400
RECORD_DEAD_LETTER_SECONDS = 14 * 86400


def batch_held_dead_letter_enabled() -> bool:
    """Ship-on record/held deadlines and expiry; manual requeue remains available when off."""
    from config.policy.kill_switches import kill_switch

    return kill_switch('BATCH_HELD_DEAD_LETTER_ENABLED')


def projection_source_deleted_enabled() -> bool:
    """Ship-on no-text settlement for a deleted source without a tombstone or redirect."""
    return rollout_default_on(
        'BATCH_PIPELINE_PROJECTION_SOURCE_DELETED_ENABLED',
        os.getenv('BATCH_PIPELINE_PROJECTION_SOURCE_DELETED_ENABLED', 'true').strip().lower() != 'false',
    )


def projection_ghost_settle_enabled() -> bool:
    """Default OFF: normalize aged ghost hints; production enable needs David."""
    return kill_switch('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED')


def projection_restorable_cap_expiry_enabled() -> bool:
    """Default OFF: allow the existing one-time expiry CAS for restorable capped holds."""
    return kill_switch('BATCH_PIPELINE_PROJECTION_RESTORABLE_CAP_EXPIRY_ENABLED')


def projection_ghost_settle_cohort() -> tuple[str, bool]:
    """Inert measurement label; return whether invalid config used the fallback."""
    label = os.getenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT', 'g1')
    valid = re.fullmatch(r'[A-Za-z0-9_-]{1,16}', label) is not None
    return (label, False) if valid else ('g1', True)


def projection_hold_recovery_enabled() -> bool:
    """Ship-on hold age gate and automatic redrive; false restores old behavior."""
    return rollout_default_on(
        'BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED',
        os.getenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true').strip().lower() != 'false',
    )


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


def language_inheritance_enabled() -> bool:
    """Default-on context inheritance; false restores per-piece detection input."""
    return rollout_default_on(
        'BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED',
        os.getenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', 'true').strip().lower() != 'false',
    )


def language_eligibility_enabled() -> bool:
    """Kill switch (unset is on; only ``false`` disables it).

    While legacy sync is on, a new sync upload whose conversation-or-user language
    is a named language the batch Parakeet model cannot serve stays on legacy sync
    instead of entering batch custody, where the worker language guard would
    quarantine it. Blank, ``multi`` and unknown languages are unaffected.
    ``false`` restores admitting those uploads to batch.
    """
    return rollout_default_on(
        'BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED',
        os.getenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', 'true').strip().lower() != 'false',
    )


def known_unsupported_batch_language(language: str | None) -> bool:
    """True only for a recognized language code the batch Parakeet model cannot serve.

    Lead ruling 304254: not English-only admission. Blank, ``multi``, ``auto``,
    ``und`` and any unrecognized value are unknown, never "known unsupported";
    only a code an STT provider recognizes (the stored-preference vocabulary)
    that the prerecorded Parakeet model does not support qualifies.
    """
    if not language_eligibility_enabled() or not isinstance(language, str):
        return False
    code = normalized_stt_language(language.strip())
    parakeet = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED]]
    return code in MODULATE_SUPPORTED_LANGUAGES and code not in parakeet


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


def require_record_protocol_ready() -> None:
    """One-time producer protocol cutover; never expires a pending obligation."""
    if os.getenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'false').strip().lower() != 'true':
        raise ValueError('record protocol cutover barrier closed')


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


def control_candidate_fanout(fanout: int | None = None) -> int:
    """Bound hint reads; 64 restores the previous candidate query width."""
    try:
        value = int(os.getenv('BATCH_CONTROL_CANDIDATE_FANOUT', '16') if fanout is None else fanout)
    except ValueError:
        return 16
    return min(64, max(1, value))


def admission_parallel_calls_enabled() -> bool:
    return os.getenv('BATCH_ADMISSION_PARALLEL_CALLS', 'true').strip().lower() != 'false'


def idle_poll_max_seconds() -> float:
    """Bound empty-lane backoff; 2 restores fixed polling."""
    try:
        value = float(os.getenv('BATCH_PIPELINE_IDLE_POLL_MAX_SECONDS', '10'))
    except ValueError:
        return 10.0
    return min(30.0, max(2.0, value)) if math.isfinite(value) else 10.0


SCHEDULER_SHARDS = 64


def shard_spread_enabled() -> bool:
    return os.getenv('BATCH_SHARD_SPREAD_ENABLED', 'true').strip().lower() != 'false'


def skip_unchanged_control_write_enabled() -> bool:
    """Admission skips rewriting its scheduler control shard when the append left it unchanged.

    Every admission and every pull wrote the same 64 shared shards; an identical rewrite only
    turned concurrent admissions and pulls into commit conflicts. False restores the write.
    """
    return os.getenv('BATCH_SKIP_UNCHANGED_CONTROL_WRITE_ENABLED', 'true').strip().lower() != 'false'


def pull_multi_lease_enabled() -> bool:
    return os.getenv('BATCH_PULL_MULTI_LEASE_ENABLED', 'true').strip().lower() != 'false'


def pull_busy_borrow_enabled() -> bool:
    """Ship-on: a pump's non-first lanes take backfill while every fresh shard is claimed.

    A claimed fresh shard is being served by its claimant, so a second lane that
    found only claimed fresh shards may lease recent/deep work instead of idling.
    Each pump's first lane keeps strict fresh-first. ``false`` restores strict
    fresh-first on every lane.
    """
    return os.getenv('BATCH_PULL_BUSY_BORROW_ENABLED', 'true').strip().lower() != 'false'


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


def contention_retry_enabled() -> bool:
    """Retry atomic batch Firestore contention by default; false is the kill switch."""
    return rollout_default_on(
        'BATCH_PIPELINE_CONTENTION_RETRY_ENABLED',
        os.getenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'true').strip().lower() != 'false',
    )


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

    A held unit whose Modulate recovery came back valid-empty gets one Soniox
    multilingual call inside the same paid recovery intent. Language-guarded
    recovery retains its separate switch and one-minute bound.
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


STRICT_VAD_SHADOW_PERCENT_DEFAULT = 10.0


def strict_vad_shadow_percent() -> float:
    """Sampled share of the CPU strict-VAD shadow; 0 disables, 100 restores full."""
    try:
        value = float(os.getenv('BATCH_PIPELINE_STRICT_VAD_SHADOW_PERCENT', '10').strip())
    except ValueError:
        return STRICT_VAD_SHADOW_PERCENT_DEFAULT
    if not math.isfinite(value):
        return STRICT_VAD_SHADOW_PERCENT_DEFAULT
    return min(100.0, max(0.0, value))


def strict_vad_shadow_sampled(segment_id: str) -> bool:
    """Deterministic by segment hash: a re-leased unit samples identically."""
    if not segment_id:
        return False
    from config.policy import cohort_bucket

    return cohort_bucket(segment_id, '') < strict_vad_shadow_percent()


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


SERVING_METRICS_MIN_REFRESH_DEFAULT = 30.0
SERVING_METRICS_MIN_REFRESH_MAX = 60.0


def serving_metrics_min_refresh_seconds() -> float:
    """Ship-on: one queue-gauge refresh per serving instance per interval.

    Every serving instance refreshed the same global gauges on each 20 s
    supervisor tick and each scrape; the policy-hold walk in ``oldest`` made
    that about 1.6M Firestore reads/h at 28 instances. The guard calls the
    sample blind after 120 s, so the cap stays at 60 s. ``off`` or a value
    <= 0 is the kill switch: refresh on every call. Malformed or out-of-range
    values keep the default.
    """
    raw = os.getenv('BATCH_PIPELINE_SERVING_METRICS_MIN_REFRESH_SECONDS', '').strip().lower()
    if not raw:
        return SERVING_METRICS_MIN_REFRESH_DEFAULT
    if raw == 'off':
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return SERVING_METRICS_MIN_REFRESH_DEFAULT
    if value <= 0:
        return 0.0
    return value if 1 <= value <= SERVING_METRICS_MIN_REFRESH_MAX else SERVING_METRICS_MIN_REFRESH_DEFAULT


ALLOWANCE_HOLD_RETRY_DEFAULT_SECONDS = 1800
ALLOWANCE_HOLD_RETRY_MAX_SECONDS = 86400


def allowance_hold_retry_seconds() -> int:
    """Ship-on re-lease hold for an exhausted plan allowance or usage budget.

    An exhausted allowance is durable until the plan changes, so a held unit's
    lease + admission RPC + defer + requeue cycle runs for nothing while it
    waits; the scheduler escalation ladder keeps today's behaviour below this
    value. ``60`` restores the former short cycle (steady 300 s after
    escalation). Malformed or out-of-range values keep the default.
    """
    raw = os.getenv('BATCH_ALLOWANCE_HOLD_RETRY_SECONDS', '').strip()
    if not raw:
        return ALLOWANCE_HOLD_RETRY_DEFAULT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return ALLOWANCE_HOLD_RETRY_DEFAULT_SECONDS
    if not math.isfinite(value):
        return ALLOWANCE_HOLD_RETRY_DEFAULT_SECONDS
    return int(value) if 1 <= value <= ALLOWANCE_HOLD_RETRY_MAX_SECONDS else ALLOWANCE_HOLD_RETRY_DEFAULT_SECONDS


def projection_pagination_enabled() -> bool:
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED')


def projection_striping_enabled() -> bool:
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED')


PROJECTION_FINISH_BACKOFF_SECONDS = (60.0, 300.0, 900.0)


def projection_finish_backoff_enabled() -> bool:
    """Default off; only ``true`` defers an unchanged persisted/ready finish walk.

    Off keeps the legacy query and disables no-change deferral transactions.
    Clock writes on state transitions are unconditional on every writer host.
    On uses the due-clock filter only after the shared backfill marker exists;
    until then it keeps the legacy page without per-row stamping. Rollback and
    re-enable are safe because flag-off writers keep maintaining the clock.
    """
    from config.policy import kill_switch

    return kill_switch('BATCH_PROJECTION_FINISH_BACKOFF_ENABLED')


def projection_finish_backoff_delay(step: int) -> float:
    """60 s, then 300 s, then 900 s for a repeatedly unchanged row; capped."""
    index = max(0, min(int(step), len(PROJECTION_FINISH_BACKOFF_SECONDS) - 1))
    return PROJECTION_FINISH_BACKOFF_SECONDS[index]


PROJECTION_DISCOVERY_STRIPES = 4096
_projection_discovery_stripe_value: int | None = None
_PROJECTION_DISCOVERY_LOCK = threading.Lock()


def projection_discovery_stripe() -> int:
    """Choose and log one process-local random phase, without network I/O.

    Replicas may share hostname/PID. Fresh entropy separates them; 4096 buckets
    reduce collisions at 30-50 instances. Restarts may choose a different phase.
    """
    global _projection_discovery_stripe_value
    with _PROJECTION_DISCOVERY_LOCK:
        if _projection_discovery_stripe_value is None:
            identity = f'{os.getenv("K_REVISION", "")}:{secrets.randbits(128)}'
            _projection_discovery_stripe_value = (
                int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], 'big') % PROJECTION_DISCOVERY_STRIPES
            )
            logging.getLogger(__name__).info(
                'event=batch_projection_discovery action=start stripe=%d stripes=%d',
                _projection_discovery_stripe_value,
                PROJECTION_DISCOVERY_STRIPES,
            )
        return _projection_discovery_stripe_value


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


def provider_backlog_release_closed() -> bool:
    """Live close-only override for the metered gate; unset never opens a gate."""
    return os.getenv('BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED', '').strip().lower() == 'false'


def provider_backlog_release_enabled() -> bool:
    """Opt-in: the ordered merge may commit provider-route catch-up rows.

    Off (the default), a provider row that is not stamped fresh at admission stays
    ``result_ready``: only an owner's fresh provider rows commit, through fresh-first. On
    2026-11-13 the first hour of provider merge membership released about 230,000 already
    transcribed backlog rows an hour; they filled the projection owner queue, which has no
    fresh class, and 45% of every user's fresh results were still unprojected 10-20 minutes
    after commit. The backlog is released by a metered job, not by owner wakes. ``true``
    restores release paced only by the catch-up depth hold.
    """
    from config.refactor_modes import default_off

    return default_off('BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED')


def provider_fresh_capture_lag_seconds() -> int:
    """Longest capture-to-admission lag at which a provider-route upload is still fresh (2026-11-13).

    Default 86400. The GPU lane keeps ``FRESH_CAPTURE_LAG_SECONDS`` (600). While the provider
    backlog is held, a provider row not stamped fresh does not commit, and it cannot commit in
    plain order either because the owner's held rows sit in front of it. With the shared
    10-minute bar, every provider upload that arrived late was therefore not delivered: 167 of
    1,195 provider admissions in 36 minutes on 2026-11-13, 103 of them within a day of capture,
    none committed. A device that was offline for a day and then syncs is normal use.
    ``600`` restores the shared bar; values are clamped to 600-86400.
    """
    return _pump_bound(os.getenv('BATCH_PIPELINE_PROVIDER_FRESH_CAPTURE_LAG_SECONDS', '86400'), 86400, 86400, 600)


def provider_merge_membership_enabled() -> bool:
    """Kill switch: provider-route units take part in the ordered merge the way GPU units do.

    Provider admission stamps ``fresh_capture``, provider settle stamps ``ready_at`` and wakes
    one coalesced owner drain, and provider rows admitted before the stamp count as catch-up.
    Without these, a settled provider unit was found only by the 100-row maintenance page and
    could never use the head wait or fresh-first (2026-11-13: 1.68M transcribed provider units
    unmerged, 97-100% of each day's settles). Off restores the earlier behaviour for new writes;
    rows already stamped keep their fields.
    """
    from config.policy import kill_switch

    # Read several times per merge transaction attempt: no per-read switch log.
    return kill_switch('BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED', log=False)


def recovery_owner_only_enabled() -> bool:
    """Kill switch: post-recovery requests drain their owner without global maintenance."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_RECOVERY_OWNER_ONLY_ENABLED')


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


def projection_followup_page_enabled() -> bool:
    """Kill switch: discover only finishable receipts, without per-row fetches."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED')


def owner_drain_enabled() -> bool:
    """Kill switch: a per-process owner drain replaces the sweep-shared walk budget."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_OWNER_DRAIN_ENABLED')


def serving_projection_sweep_enabled() -> bool:
    """Only ``off`` disables serving-instance discovery; owner wakes still run."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_SERVING_PROJECTION_SWEEP')


def _pump_bound(raw: str, default: int, maximum: int, minimum: int = 1) -> int:
    try:
        return max(minimum, min(int(raw), maximum))
    except ValueError:
        return default


def ready_discovery_cursor_enabled() -> bool:
    return kill_switch('BATCH_PIPELINE_READY_DISCOVERY_CURSOR_ENABLED', log=False)


def ready_discovery_owners_per_tick(default: int = 20) -> int:
    return _pump_bound(os.getenv('BATCH_PIPELINE_READY_DISCOVERY_OWNERS_PER_TICK', str(default)), 20, 100)


def ready_discovery_tick_seconds() -> int:
    return _pump_bound(os.getenv('BATCH_PIPELINE_READY_DISCOVERY_TICK_SECONDS', '10'), 10, 60)


def serving_sweep_page_rows() -> int:
    """Bound projection discovery pages; unset restores the existing 100 rows."""
    return _pump_bound(os.getenv('BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS', '100'), 100, 200, 50)


_serving_budget_warned = False
_SERVING_BUDGET_WARNING_LOCK = threading.Lock()


def _serving_effective_tick(page_rows: int, requested_tick: int) -> float:
    """Never reduce discovery pages to meet the 20 rows/s supervisor budget."""
    global _serving_budget_warned
    budget_tick = page_rows / 20
    effective_tick = max(10, requested_tick, budget_tick)
    if requested_tick < budget_tick:
        with _SERVING_BUDGET_WARNING_LOCK:
            if not _serving_budget_warned:
                _serving_budget_warned = True
                logging.getLogger(__name__).warning(
                    'event=batch_serving_config action=read_budget requested_tick_seconds=%d '
                    'effective_page_rows=%d effective_tick_seconds=%g max_rows_per_second=20',
                    requested_tick,
                    page_rows,
                    effective_tick,
                )
    return effective_tick


def serving_tick_seconds() -> float:
    """Clamp sleep to 10-60 s and enforce the combined serving discovery budget."""
    requested_tick = _pump_bound(os.getenv('BATCH_PIPELINE_SERVING_TICK_SECONDS', '20'), 20, 60, 0)
    return _serving_effective_tick(serving_sweep_page_rows(), requested_tick)


def projection_pump_enabled() -> bool:
    """Process-role opt-in: only ``true`` starts the otherwise inert pump."""
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED')


def projection_pump_tick_seconds() -> int:
    return _pump_bound(os.getenv('BATCH_PIPELINE_PUMP_TICK_SECONDS', '20'), 20, 60, 2)


def projection_pump_sweep_pages() -> int:
    return _pump_bound(os.getenv('BATCH_PIPELINE_PUMP_SWEEP_PAGES', '1'), 1, 4)


def max_owner_drains() -> int:
    return _pump_bound(os.getenv('BATCH_PIPELINE_MAX_OWNER_DRAINS', '8'), 8, 16)


def projection_recent_discovery_seconds() -> int:
    """Seconds of the newest commits that up to half of each assignment discovery page
    reads from (2026-11-13); 0 is off.

    Discovery pages the pending results oldest first, 100 rows a tick per process. With
    154,000 pending rows a newly committed result waited about 15 minutes to be seen at
    all, and GPU-route commits have no other wake. Each tick now also reads up to half a
    page from a random point inside this window and offers each row there once per
    process; the rest of the page keeps walking the whole log. 0 restores the single
    cursor and removes the main cursor's 30-minute restart."""
    return _pump_bound(os.getenv('BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS', '120'), 120, 3600, 0)


def owner_drain_first_turn_seconds() -> int:
    """Seconds a newly requested owner's first projection turn may run (2026-11-13); 0 is off.

    A productive turn that ends with rows left makes its owner a backlog owner. Backlog
    owners keep the full two-minute turn but wait in their own queue, behind newly
    requested owners, and end a turn at the next step when one of those is waiting for a
    slot. Without this a few hundred backlog owners hold every slot for two minutes each
    and an owner with a handful of fresh rows waits behind all of them. 0 restores the
    single FIFO queue."""
    return _pump_bound(os.getenv('BATCH_PIPELINE_OWNER_DRAIN_FIRST_TURN_SECONDS', '15'), 15, 120, 0)


def projection_drain_claim_aware_enabled() -> bool:
    """Default on; only off disables claim-aware owner-drain admission and backoff."""
    from config.policy import kill_switch

    return kill_switch('PROJECTION_DRAIN_CLAIM_AWARE')


def projection_drain_privacy_backoff_enabled() -> bool:
    """Default on; only off disables zero-progress privacy turn backoff."""
    from config.policy import kill_switch

    return kill_switch('PROJECTION_DRAIN_PRIVACY_BACKOFF')


def projection_drain_live_target_backoff_enabled() -> bool:
    """Default on; only off disables bounded awaiting-live-target owner backoff."""
    return kill_switch('PROJECTION_DRAIN_LIVE_TARGET_BACKOFF')


def projection_privacy_refusal_resume_enabled() -> bool:
    """Default on; only off disables recovery from a stale privacy refusal."""
    return kill_switch('PROJECTION_PRIVACY_REFUSAL_RESUME')


def projection_drain_privacy_backoff_seconds() -> int:
    return _pump_bound(os.getenv('PROJECTION_DRAIN_PRIVACY_BACKOFF_SECONDS', '180'), 180, 900, 30)


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


PROJECTION_FOLLOWUP_SLOTS_DEFAULT = 4
PROJECTION_FOLLOWUP_SLOTS_MAX = 16


def projection_followup_slots(default: int = PROJECTION_FOLLOWUP_SLOTS_DEFAULT) -> int:
    """Concurrent async follow-ups per serving process; unset, malformed or out-of-range keeps ``default``."""
    raw = os.getenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_SLOTS', '').strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return value if 1 <= value <= PROJECTION_FOLLOWUP_SLOTS_MAX else default


PROJECTION_FOLLOWUP_BACKOFF_DEFAULT = 900.0
PROJECTION_FOLLOWUP_BACKOFF_MAX = 3600.0


def projection_followup_backoff_seconds() -> float:
    """Ship-on follow-up desync: per-process discovery offset plus bounded backoff; ``0`` is the kill switch.

    The value is the longest one process skips an unchanged blocked/failed row
    in its own discovery. ``0`` restores head-first discovery with no backoff.
    Malformed or out-of-range values keep the default.
    """
    try:
        value = float(
            os.getenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_BACKOFF_SECONDS', str(PROJECTION_FOLLOWUP_BACKOFF_DEFAULT))
        )
    except ValueError:
        return PROJECTION_FOLLOWUP_BACKOFF_DEFAULT
    if not math.isfinite(value) or not 0 <= value <= PROJECTION_FOLLOWUP_BACKOFF_MAX:
        return PROJECTION_FOLLOWUP_BACKOFF_DEFAULT
    return value


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


WORKER_PROCESSES_DEFAULT = 1
WORKER_PROCESSES_MAX = 3


def worker_processes() -> int:
    """Independent pump processes sharing the pod's one GPU; ``1`` (default) runs no supervisor.

    Each process loads its own model chain and keeps its own pump depth and
    decoded-audio bound, so host and device memory scale with the count; the
    chart sizes pod resources per count. Malformed or out-of-range values run
    one process: a typo must never multiply the pod's memory.
    """
    try:
        value = int(os.getenv('BATCH_PIPELINE_WORKER_PROCESSES', str(WORKER_PROCESSES_DEFAULT)))
    except ValueError:
        return 1
    return value if 1 <= value <= WORKER_PROCESSES_MAX else 1


WORKER_IO_CONCURRENCY_DEFAULT = 5
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
    """Shared bounded artifact fetch/decode and persistence across pump lanes.

    1 restores the fully serial chain. Malformed or out-of-range values keep the
    bounded default; GPU work and the chain lock are unaffected either way.
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
