"""Default-off batch admission cohort. Existing lane classification stays upstream."""

from config.refactor_switches import default_off as rollout_default_off, default_on as rollout_default_on

from enum import IntEnum
import math
import os

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


def pull_multi_lease_enabled() -> bool:
    return os.getenv('BATCH_PULL_MULTI_LEASE_ENABLED', 'true').strip().lower() != 'false'


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


def contention_storm_damper_enabled() -> bool:
    """Space re-strikes of an exhausted operation by default; false is the kill switch.

    The bounded retry chain gives one operation five immediate attempts across
    roughly one to three seconds; during a real contention storm every caller
    that exhausts re-strikes the same hot document at once and the whole fleet
    burns budget in lockstep. The store-level storm damper (see
    ``database/batch_pipeline_store.py``) arms a bounded, jittered per-label
    backoff after an exhaustion so the next entry of that same operation waits
    out the residual window instead of colliding again.
    """
    return rollout_default_on(
        'BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
        os.getenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'true').strip().lower() != 'false',
    )


def persist_restrike_enabled() -> bool:
    """Re-strike a transport-lost worker persist in-process by default; false is the kill switch.

    The worker's persist stage encrypts and uploads the completed unit result
    through the staging bucket and the durable artifact register. When that
    transport faults (a Google API ``InvalidArgument``/5xx burst from the
    storage or register hop), the worker today discards a fully produced GPU
    result — decode, VAD, diarization and ASR all done — and books a transient
    worker fault, so lease recovery re-leases the unit and re-runs the entire
    GPU chain to reproduce a result the worker already held (the
    ``event=batch_worker_failed error_class=InvalidArgument stage=persist``
    sensor family, joined by its bare ``error_class=TimeoutError`` siblings:
    the upload stream's 15-minute deadline, the 30-second registration grace
    and raw socket timeouts raise the builtin ``TimeoutError``, which no
    Google API class hierarchy covers). With this gate on, the persist
    boundary re-plays the same persist call in-process with a documented
    doubling backoff (0.25s -> 2.0s, at most three strikes) while the worker
    still holds the sealed payload: the durable deletion outbox registers each
    attempt before its upload, so a strike that never lands leaves the same
    registered-but-unwritten reference the uncertain-upload path already
    tolerates, and a strike that lands returns its own immutable URI. Only the
    Google API transport family and the builtin ``TimeoutError`` transport
    family classify as re-strikeable losses; typed custody faults
    (StagedAudioInvalid and siblings), privacy fences, policy refusals and
    every other non-Google exception abort the lane and the legacy fail path
    runs byte-for-byte as before. false restores the immediate fault for every
    loss.

    Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
    """
    return rollout_default_on(
        'BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED',
        os.getenv('BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED', 'true').strip().lower() != 'false',
    )


def publication_restrike_enabled() -> bool:
    """Re-strike a contention-lost publication transition in-process by default; false is the kill switch.

    The worker pump's publication transitions (``batch_complete``,
    ``batch_fail``, ``batch_defer``) are lease-fenced single-document
    transactions. When one exhausts its store-level five-attempt
    contention budget, the pump today discards a completed GPU result and
    waits for lease-expiry recovery to re-lease the unit — which re-runs
    the whole GPU chain to re-produce a result the pump already held
    (the ``event=batch_completion outcome=retry
    exception_type=FirestoreContentionExhausted`` sensor family). With
    this gate on, the pump's bounded re-strike lane replays the same
    fenced transition with a documented doubling backoff (0.25s -> 2.0s,
    at most three re-strikes) while the 120-second lease still holds;
    every re-strike is authorized by the production ``owns_lease`` fence,
    so a lease that died mid-lane is rejected exactly like a stale
    replay. Only the bounded contention budget classifies as a
    re-strikeable loss; any other exception aborts the lane and the
    legacy catch site (lost marker + terminal ERROR line) runs
    byte-for-byte as before. The store-level storm damper still spaces
    the re-strike behind an armed exhaustion window; false restores the
    immediate fallback for every loss.

    Failure-Class: FC-publication-contention-discards-completed-gpu-results
    """
    return rollout_default_on(
        'BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED',
        os.getenv('BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED', 'true').strip().lower() != 'false',
    )


def maintenance_contention_continuation_enabled() -> bool:
    """Continue the maintenance sweep past a contended step or item by default; false is the kill switch.

    The maintenance tick (``utils/batch_pipeline/pump.py`` ``_maintain``) and the
    lease-expiry recovery loop (``utils/batch_pipeline/scheduler.py``
    ``recover``) run independent steps and per-item transactions in a fixed
    order. One exhausted contention budget used to abort the whole sweep at the
    failing step, so the 1-second loop re-struck the same hot document while
    every step behind it — the result_ready drain, the durable hold markers,
    every expired lease behind the failing item — stayed starved. With this
    gate on, the step or item logs its own bounded outcome and the sweep
    continues; the lost work retries at the next sweep (>=5s later) and the
    store-level storm damper spaces the re-strike.
    """
    return rollout_default_on(
        'BATCH_PIPELINE_MAINTENANCE_CONTINUATION_ENABLED',
        os.getenv('BATCH_PIPELINE_MAINTENANCE_CONTINUATION_ENABLED', 'true').strip().lower() != 'false',
    )


def fifo_array_link_enabled() -> bool:
    """Keep the owner FIFO link on the queue document by default; false is the kill switch.

    The legacy representation stores each unit's ``next`` pointer on its
    predecessor's job document, so every append read-modify-writes the
    in-flight tail unit's lifecycle-hot document and collides with its
    heartbeat, completion and failure transitions. The queue-document array
    removes the job document from the append write set entirely. The flag
    gates conversion only: queues already converted always drain through the
    array-aware walk, so flipping the flag never strands queued units.
    """
    return rollout_default_on(
        'BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED',
        os.getenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', 'true').strip().lower() != 'false',
    )


def control_steady_write_skip_enabled() -> bool:
    """Skip the control-document write when admission activation changes nothing; false is the kill switch.

    Every unit admission of an already-active owner appended the owner's
    control document with byte-identical content: ``activate`` is
    value-stable on the warm path (``active`` stays set, service is seeded
    once at the cold frontier, both availability floors only ever move
    down) and a warm queue's ring membership does not change. Under
    sibling admission bursts those content-free writes carried the
    hottest per-owner document inside every append transaction's write
    set, so N concurrent sibling appends aborted each other through the
    shared five-attempt budget — the ``firestore_transaction_contention
    operation=batch_pipeline_store attempt=5/5 outcome=exhausted`` storm
    family. The skip turns the write into a decision: identical snapshot
    → no write (the abort set loses a member and the queue/job writes
    keep their budget), any real activation change → the write,
    byte-for-byte as before. Pull-grant service advances and cold
    activations are real changes and always write.

    Failure-Class: FC-control-document-carries-content-free-append-writes
    """
    return rollout_default_on(
        'BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED',
        os.getenv('BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED', 'true').strip().lower() != 'false',
    )


def shadow_slot_cas_enabled() -> bool:
    """Arbitrate the shadow slot ring with conditional writes by default.

    The shared batch contention kill switch is opt-out for the whole
    contention family: false restores the transactional four-slot ring that
    reads every slot in one transaction. Point-read-plus-fenced-write
    arbitration shares no transaction read set, so concurrent
    offer/take/reserve cycles cannot abort one another into
    ``firestore_transaction_contention ... outcome=exhausted``.
    """
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


def merge_narrow_commit_enabled() -> bool:
    """Plain ready-head merge drains commit through fenced point reads by default.

    The strict body opens the transactional pending query for every drain, and
    that query's read set is every matched row — the documents each sibling
    lease heartbeat (every 20 seconds per in-flight unit) keeps rewriting — so
    a ready-head drain burned its whole five-attempt ladder against sibling
    heartbeats (``event=batch_merge outcome=retry
    exception_type=FirestoreContentionExhausted``). The narrow body commits the
    probed head through owner/head/result point reads under a probed owner
    revision fence and falls back to the strict body on any mismatch; ``false``
    is the kill switch and restores the strict query for every drain.
    """
    return rollout_default_on(
        'BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED',
        os.getenv('BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED', 'true').strip().lower() != 'false',
    )


def merge_held_head_gate_enabled() -> bool:
    """Held owners with a ready catch-up head skip the strict hold re-decide by default.

    An owner parked at the projection depth cap carries a durable hold marker,
    and the pump re-drains it from three directions every cycle: after each of
    its unit completions, through the global result_ready page, and through the
    marked-owner re-offer. Every one of those drains used to open the strict
    ``batch_merge_commit`` transaction whose first act is the owner's pending
    query — a query-in-transaction read set is every matched row, the documents
    each sibling lease heartbeat keeps rewriting — only to re-conclude
    ``held`` and write nothing (``event=batch_merge outcome=retry
    exception_type=FirestoreContentionExhausted``). When outside-transaction
    probes positively prove that conclusion (the probed head is this owner's
    pending catch-up row in ``result_ready``, the probed owner still sits at
    the cap, and the probed durable marker is already set), the drain skips
    the transaction and records the same held facts the body would have; a
    ready fresh row still commits through the unchanged fresh-first re-verify
    below. ``false`` is the kill switch and restores the strict re-decide for
    every held-owner drain.
    """
    return rollout_default_on(
        'BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED',
        os.getenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'true').strip().lower() != 'false',
    )
