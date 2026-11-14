"""Closed reason vocabularies for metric labels, durable diagnostics and logs.

Contract (e) of the backend target architecture. Rules:

* Values are ``lower_snake``, at most 40 characters and content-free (no ids,
  no exception text).
* Every family has ``UNKNOWN = 'unknown'``.
* Class names end in ``Reason``, ``Stage`` or ``Outcome``.
* Metric labels take only enum members (see ``reason_label``) or a ``bounded_*``
  helper for builds and providers.

``reason_label`` never raises on a serving path. A non-member is counted in
``omi_reason_unknown_total{family}`` and returned as ``'unknown'``. The alert
(``omi:reason_unknown_ratio:rate30m{family}`` above 2% for 30 minutes) is
shipped by the Observability session's repo==live pipeline, not here.

This module must stay import-light: it is imported by ``utils.stt.live_reason``
and the batch-pipeline constants modules.
"""

from __future__ import annotations

import re
from enum import StrEnum

from prometheus_client import Counter

REASON_VALUE_MAX_LENGTH = 40


class ServerBatchSuppressionReason(StrEnum):
    UNKNOWN = 'unknown'
    SUPPRESSED = 'suppressed'
    LANGUAGE_AUTO = 'language_auto'
    LANGUAGE_UNSUPPORTED = 'language_unsupported'
    PROFILE_MISMATCH = 'profile_mismatch'
    PRIVATE_SYNC_OFF = 'private_sync_off'
    CUSTOM_STT = 'custom_stt'
    MULTI_CHANNEL = 'multi_channel'
    PHONE_CALL = 'phone_call'
    ONBOARDING = 'onboarding'
    PUSHER_UNAVAILABLE = 'pusher_unavailable'
    CAPTURE_NOT_OWNED = 'capture_not_owned'
    PLATFORM_UNSELECTED = 'platform_unselected'
    NOT_ENABLED = 'not_enabled'


class MemoryL1Reason(StrEnum):
    NOISE = 'noise'
    SHORT_OWNER_SPEECH = 'short_owner_speech'
    UNKNOWN = 'unknown'


class ReasonFamily(StrEnum):
    MEMORY_L1 = 'memory_l1'
    PUSHER_PCM = 'pusher_pcm'
    LIVE_STT = 'live_stt'
    WORKER_VALIDATION = 'worker_validation'
    RECOVERY_FAILURE = 'recovery_failure'
    STALE_RECOVERY = 'stale_recovery'
    WORK_OUTCOME = 'work_outcome'
    QUARANTINE = 'quarantine'
    FALLBACK = 'fallback'
    RETRY = 'retry'
    CONSUMER = 'consumer'
    PROVIDER_STT = 'provider_stt'
    RAMP = 'ramp'
    LEGACY_DARK = 'legacy_dark'
    PARITY = 'parity'
    STAGING_FENCE = 'staging_fence'
    HELD_CONTENT = 'held_content'
    SPEAKER_EVIDENCE = 'speaker_evidence'
    NOTES_AGENT_FORCE = 'notes_agent_force'
    NOTES_AGENT_TRANSPORT = 'notes_agent_transport'
    SYNC_DISPATCH = 'sync_dispatch'
    SYNC_CAPTURE_TIME = 'sync_capture_time'
    SYNC_BRIDGE_CONTAINMENT = 'sync_bridge_containment'
    SYNC_PROCESSING_HOLD = 'sync_processing_hold'
    ADMISSION_HOLD = 'admission_hold'
    LISTEN_SESSION_TRANSCRIPT = 'listen_session_transcript'
    RECORD_PARTIAL_RERUN = 'record_partial_rerun'
    VENDOR_ROUTE = 'vendor_route'
    DELIVERY = 'delivery'
    BATCH_FINAL_PASS = 'batch_final_pass'
    RECURRING_VOICE = 'recurring_voice'
    RECORD_GAP_FILL = 'record_gap_fill'
    RECORD_RETAINED_ACK = 'record_retained_ack'
    PIPELINE_LEDGER = 'pipeline_ledger'
    JOURNEY_FAILURE = 'journey_failure'
    LISTEN_NO_AUDIO_CLOSE = 'listen_no_audio_close'
    DUE_MARKER_SWEEP = 'due_marker_sweep'


class PusherPcmStage(StrEnum):
    UNKNOWN = 'unknown'
    LIVE = 'live'
    TAIL = 'tail'


class PusherPcmErrorReason(StrEnum):
    UNKNOWN = 'unknown'
    ACQUIRE = 'acquire'
    RELEASE = 'release'
    LATE_STORAGE = 'late_storage'


REASON_UNKNOWN_TOTAL = Counter(
    'omi_reason_unknown_total',
    'Values presented to a closed reason enum that were not members, by reason family',
    ['family'],
)
OMI_REASON_TOTAL = Counter(
    'omi_reason_total',
    'Values presented to a closed reason enum (denominator for omi:reason_unknown_ratio:rate30m), by reason family',
    ['family'],
)


for _family in ReasonFamily:  # pre-initialise children so rate() sees them from the first scrape
    REASON_UNKNOWN_TOTAL.labels(family=_family.value)
    OMI_REASON_TOTAL.labels(family=_family.value)


class RecordGapFillOutcome(StrEnum):
    """One closed-record gap-fill attempt (``utils.batch_pipeline.record_gap_fill``)."""

    UNKNOWN = 'unknown'
    WRITTEN = 'written'
    SKIPPED_GATE = 'skipped_gate'
    SKIPPED_RECENT = 'skipped_recent'
    SKIPPED_MARKER = 'skipped_marker'
    SKIPPED_NO_PENDING = 'skipped_no_pending'
    SKIPPED_RETAINED = 'skipped_retained'
    SKIPPED_NO_GAP = 'skipped_no_gap'
    SKIPPED_NO_AUDIO = 'skipped_no_audio'
    SKIPPED_NOT_CONTIGUOUS = 'skipped_not_contiguous'
    SKIPPED_COLLISION = 'skipped_collision'
    SKIPPED_BUSY = 'skipped_busy'
    RACED = 'raced'
    FAILED = 'failed'


class RecordRetainedAckOutcome(StrEnum):
    """One option A byte-exact retained-copy proof (``utils.batch_pipeline.record_retained_ack``)."""

    UNKNOWN = 'unknown'
    ACKED = 'acked'
    SKIPPED_FILL = 'skipped_fill'
    SKIPPED_UNCOVERED = 'skipped_uncovered'
    SKIPPED_LOSSY_SOURCE = 'skipped_lossy_source'
    SKIPPED_BYTES_DIFFER = 'skipped_bytes_differ'
    SKIPPED_OUTSIDE_RECORD = 'skipped_outside_record'
    SKIPPED_BOUNDS = 'skipped_bounds'
    SKIPPED_PRIVACY = 'skipped_privacy'
    FAILED = 'failed'


class DeliveryOutcome(StrEnum):
    UNKNOWN = 'unknown'
    DELIVERED = 'delivered'
    NO_OP = 'no_op'
    DEFERRED = 'deferred'
    FAILED = 'failed'


class SyncProcessingHoldOutcome(StrEnum):
    UNKNOWN = 'unknown'
    QUIET_WAIT = 'quiet_wait'
    WATERMARK_WAIT = 'watermark_wait'
    READY = 'ready'
    MAX_HOLD = 'max_hold'
    UNCHANGED = 'unchanged'
    IMMATERIAL = 'immaterial'
    LATE_CAP = 'late_cap'


class ListenSessionTranscriptOutcome(StrEnum):
    """One listen session's headline transcript outcome (``ListenSessionRuntime._session_transcript_outcome``)."""

    UNKNOWN = 'unknown'
    TRANSCRIBED = 'transcribed'
    NO_TRANSCRIPT = 'no_transcript'
    TOO_SHORT = 'too_short'


class PersonVoiceQualityReason(StrEnum):
    UNKNOWN = 'unknown'
    INVALID_PERSON_VOICEPRINT = 'invalid_person_voiceprint'
    INSUFFICIENT_PERSON_VOICE_AUDIO = 'insufficient_person_voice_audio'
    INCOMPATIBLE_PERSON_VOICEPRINT = 'incompatible_person_voiceprint'


class StaleRecoveryOutcome(StrEnum):
    """Disposition of one reconnect stale-row finalization attempt."""

    UNKNOWN = 'unknown'
    ACCEPTED = 'accepted'
    NOT_ADMITTED = 'not_admitted'
    ERROR = 'error'
    OVERSIZED_CLOSE_ATTEMPTED = 'oversized_close_attempted'
    CURRENT_SESSION = 'current_session'
    CANCELLED = 'cancelled'


class DueMarkerSweepOutcome(StrEnum):
    """Result of re-marking one finalization job that had no due marker."""

    UNKNOWN = 'unknown'
    REMARKED = 'remarked'
    SKIPPED = 'skipped'
    ERROR = 'error'


class RetryReason(StrEnum):
    UNKNOWN = 'unknown'
    LOCKED = 'locked'
    CALLBACK_PENDING = 'callback_pending'
    PERSISTENCE_FENCED = 'persistence_fenced'
    KILL_SWITCH_OFF = 'kill_switch_off'
    CUTOVER_STANDBY = 'cutover_standby'
    DEPENDENCY_WARMING = 'dependency_warming'
    POLICY_DEFER = 'policy_defer'


class ConsumerReason(StrEnum):
    UNKNOWN = 'unknown'
    PROCESSED = 'processed'
    NOT_DUE = 'not_due'
    PRIVACY_BLOCKED = 'privacy_blocked'
    TARGET_DELETED = 'target_deleted'
    SUPERSEDED = 'superseded'
    REDIRECTED = 'redirected'
    STALE_TOKEN = 'stale_token'
    LEASE_HELD = 'lease_held'
    EMPTY_OUTPUT_BLOCKED = 'empty_output_blocked'


class RampReason(StrEnum):
    UNKNOWN = 'unknown'
    GATE_PASS = 'gate_pass'
    GATE_PENDING = 'gate_pending'
    GATE_FAIL = 'gate_fail'
    HOLD_INCOMPLETE = 'hold_incomplete'
    LOCKED_BY_OPERATOR = 'locked_by_operator'
    AT_CEILING = 'at_ceiling'
    DATA_LOSS = 'data_loss'
    PRIVACY = 'privacy'


class TransitionTailOutcome(StrEnum):
    """Disposition of a tiny cap-transition tail after its bounded grace."""

    UNKNOWN = 'unknown'
    COALESCED = 'coalesced'
    SEALED = 'sealed'


class HeldRecoverySkipOutcome(StrEnum):
    """Why a processing choice skipped a backlog item without any recovery attempt."""

    UNKNOWN = 'unknown'
    OUT_OF_SCOPE = 'out_of_scope'
    UNKNOWN_ORIGIN = 'unknown_origin'
    TEXT_OUT_OF_SCOPE = 'text_out_of_scope'
    # Intended: Free owners never recover (David, 2026-11-01). Kept out of the recovery gate.
    NOT_PAID = 'not_paid'


class BacklogChoiceOutcome(StrEnum):
    """Result of a "Process waiting recordings" tap or a Stripe trial's one-time grant."""

    UNKNOWN = 'unknown'
    ACCEPTED = 'accepted'
    OUT_OF_SCOPE = 'out_of_scope'
    NOT_PAID = 'not_paid'
    CAPPED = 'capped'
    NOTHING_WAITING = 'nothing_waiting'
    STALE_INTENT = 'stale_intent'
    ERROR = 'error'


class StagingRetryOutcome(StrEnum):
    """Disposition of a held-audio staging attempt, including volatile custody."""

    UNKNOWN = 'unknown'
    RETRIED_OK = 'retried_ok'
    DEFERRED = 'deferred'
    EXHAUSTED = 'exhausted'
    PERMANENT = 'permanent'
    RETAINED = 'retained'


class SyncDispatchFailureReason(StrEnum):
    """Closed reasons for a sync v2 staging/dispatch refusal."""

    UNKNOWN = 'unknown'
    DISPATCH_HOLD = 'dispatch_hold'
    STAGING_FAILED = 'staging_failed'


class SyncCaptureTimeReason(StrEnum):
    """Disposition of one sync upload capture time against the shared window.

    Owner: `utils/sync/capture_clock.py`. `accepted_future_skew` is a real
    capture whose phone clock runs ahead of the server within tolerance;
    `accepted_early_clamped` is a reset-clock stamp normalized to receipt time.
    `rejected_early` remains available when its kill switch is off;
    malformed stamps and beyond-tolerance future clocks stay refused.
    """

    UNKNOWN = 'unknown'
    ACCEPTED = 'accepted'
    ACCEPTED_FUTURE_SKEW = 'accepted_future_skew'
    ACCEPTED_EARLY_CLAMPED = 'accepted_early_clamped'
    REJECTED_FUTURE = 'rejected_future'
    REJECTED_EARLY = 'rejected_early'
    REJECTED_MALFORMED = 'rejected_malformed'


class ContainedDonorShadowOutcome(StrEnum):
    """`omi_sync_bridge_contained_donor_shadow_total{outcome}` for a processed sync donor.

    Owner: `utils/sync/bridge.py::_shadow_contained_donor`. The shadow count gates
    the shadow-to-on ramp, so the label is a closed enum rather than free text.
    `error` is a bounded read/compare failure: the shadow path still refuses.
    """

    UNKNOWN = 'unknown'
    WOULD_ABSORB = 'would_absorb'
    PARTIAL_OVERLAP = 'partial_overlap'
    OPEN_TARGET = 'open_target'
    NO_OVERLAP = 'no_overlap'
    NO_SEGMENT_SPAN = 'no_segment_span'
    UNPLACED_DONOR = 'unplaced_donor'
    DONOR_INELIGIBLE = 'donor_ineligible'
    ERROR = 'error'


class BatchIntakeOutcome(StrEnum):
    """`omi_batch_intake_outcome_total{outcome}`: where one v2 sync upload's batch routing landed.

    Owner: `utils/batch_pipeline/intake_outcome.py`. `batch` is an upload batch
    intake admitted fresh work; `heavy_excluded`/`language_excluded` are this
    request's fresh exclusions that landed it on legacy; `not_cohort` is the
    ramp cohort decision. An upload following a prior durable owner carries no
    fresh decision and is not counted.
    """

    UNKNOWN = 'unknown'
    BATCH = 'batch'
    HEAVY_EXCLUDED = 'heavy_excluded'
    LANGUAGE_EXCLUDED = 'language_excluded'
    NOT_COHORT = 'not_cohort'


class AdmissionHoldReason(StrEnum):
    """Closed reasons a compute-admission lease was held at defer time.

    Owner: `utils/batch_pipeline/admission.py`. The literals are that module's
    fair-use/ceiling/reservation/privacy holds; the spend-gate members mirror
    the refusal subset of `utils.observability.stt_cap_dispatch.DispatchReason`.
    Anything else folds to `unknown` by `reason_label`, never free text.
    """

    UNKNOWN = 'unknown'
    FAIR_USE_RESTRICTED = 'fair_use_restricted'
    DAILY_AUDIO_CEILING = 'daily_audio_ceiling'
    BACKFILL_RESERVATION = 'backfill_reservation'
    PRIVACY_BLOCKED = 'privacy_blocked'
    CONSENT_DENIED = 'consent_denied'
    ALLOWANCE_EXHAUSTED = 'allowance_exhausted'
    BUDGET_EXHAUSTED = 'budget_exhausted'
    ALLOWANCE_UNAVAILABLE = 'allowance_unavailable'
    ACCESS_DENIED = 'access_denied'


class WorkOutcome(StrEnum):
    """`WorkResult.outcome` tokens (`utils/batch_pipeline/contracts.py`)."""

    UNKNOWN = 'unknown'
    SUCCESS = 'success'
    SILENCE = 'silence'
    NO_RECOVERABLE_SPEECH = 'no_recoverable_speech'


class BatchFinalPassOutcome(StrEnum):
    """Fallback outcomes of the batch whole-conversation pass (`utils/conversations/final_pass_batch.py`)."""

    UNKNOWN = 'unknown'
    SKIPPED_BUDGET = 'skipped_budget'
    SKIPPED_EXPIRED = 'skipped_expired'
    SKIPPED_MERGED = 'skipped_merged'
    SHARED_UNIT = 'skipped_shared_unit'
    REQUEUE = 'failed_requeue'
    SLOT_EXHAUSTED = 'skipped_slot_exhausted'
    RETRY_EXHAUSTED = 'skipped_retry_exhausted'
    FAILED_DEPENDENCY = 'failed_dependency'
    SKIPPED_NO_CHANGES = 'skipped_no_changes'
    TOO_LONG = 'failed_too_long'
    READ_BUDGET = 'failed_read_budget'
    INCOMPLETE_COVERAGE = 'failed_incomplete_coverage'
    PARTIAL_COVERAGE = 'partial_coverage'
    BATCH_AUDIO = 'failed_batch_audio'
    INCOMPATIBLE_SPACE = 'failed_incompatible_space'
    REVOKED = 'failed_revoked'
    UNASSIGNED_WORDS = 'failed_unassigned_words'


class QuarantineReason(StrEnum):
    """`quarantine_reason` stored on a batch job. `worker_failed` is the only writer today."""

    UNKNOWN = 'unknown'
    WORKER_FAILED = 'worker_failed'


class RefactorShadowOutcome(StrEnum):
    """Shared capture/speaker/lifecycle comparison vocabulary."""

    UNKNOWN = 'unknown'
    AGREE = 'agree'
    DISAGREE = 'disagree'
    ERROR = 'error'


class CaptureCoverageOutcome(StrEnum):
    """Exact frame admission and skipped-seconds dispositions."""

    UNKNOWN = 'unknown'
    COVERED = 'covered'
    PARTIAL = 'partial'
    UNCOVERED = 'uncovered'
    SKIPPED = 'skipped'
    WOULD_SKIP = 'would_skip'


class ShadowParityOutcome(StrEnum):
    """`omi_jobstore_shadow_parity_total{outcome}` (lane 12, Postgres shadow-write parity)."""

    UNKNOWN = 'unknown'
    MATCH = 'match'
    MISMATCH = 'mismatch'
    MISSING = 'missing'
    EXTRA = 'extra'
    UNCOMPARABLE = 'uncomparable'
    MIRRORED = 'mirrored'
    ERROR = 'error'
    TIMEOUT = 'timeout'
    DROPPED = 'dropped'
    SKIPPED = 'skipped'


class ShadowConvergenceOutcome(StrEnum):
    """`omi_jobstore_shadow_convergence_total{outcome}` (lane 12, A2 gate: mirror lag vs divergence)."""

    UNKNOWN = 'unknown'
    CONVERGED = 'converged'
    DIVERGED = 'diverged'
    DROPPED = 'dropped'
    ERROR = 'error'


class ProviderSttReason(StrEnum):
    """Lane 8 owns the member list; the base set is the pre-recorded provider-STT stage vocabulary."""

    UNKNOWN = 'unknown'
    NONE = 'none'
    BYOK = 'byok'
    UNSUPPORTED_LANGUAGE = 'unsupported_language'
    PROVIDER_FAILED = 'provider_failed'


# All-vendor batch routing (utils/batch_pipeline/vendor_route_contracts.py). Slice A froze
# these member lists; a slice that needs a new value posts the change before adding it.


class VendorRouteReason(StrEnum):
    """Why selection chose a route: ``omi_batch_pipeline_vendor_route_decisions_total{route,reason}``."""

    UNKNOWN = 'unknown'
    CHEAPEST = 'cheapest'
    ORDERED = 'ordered'
    GPU_FLOOR = 'gpu_floor'
    SOLE_CAPABLE = 'sole_capable'
    FAILOVER = 'failover'
    NO_HEALTHY_ROUTE = 'no_healthy_route'
    GPU_OVERFLOW = 'gpu_overflow'
    KILL_SWITCH = 'kill_switch'
    NOT_IN_COHORT = 'not_in_cohort'


class VendorRouteTableOutcome(StrEnum):
    """Which rung of the table ladder served: ``..._vendor_route_table_loads_total{outcome}``."""

    UNKNOWN = 'unknown'
    CONFIGURED = 'configured'
    LAST_VALID = 'last_valid'
    BUILTIN = 'builtin'


class VendorHealthReason(StrEnum):
    """Second element of ``VendorHealth.allows(service)``."""

    UNKNOWN = 'unknown'
    HEALTHY = 'healthy'
    HALF_OPEN_PROBE = 'half_open_probe'
    DEGRADED = 'degraded'
    BREAKER_OPEN = 'breaker_open'
    FUNDS_REFUSAL = 'funds_refusal'
    RATE_LIMITED = 'rate_limited'
    DAILY_CAP_REACHED = 'daily_cap_reached'
    MONTHLY_BUDGET_REACHED = 'monthly_budget_reached'
    NOT_ADMITTED = 'not_admitted'
    STATE_UNAVAILABLE = 'state_unavailable'


class VendorAttemptOutcome(StrEnum):
    """One vendor attempt's outcome: ``..._vendor_attempts_total{provider,outcome}``."""

    UNKNOWN = 'unknown'
    RUNNING = 'running'
    OK = 'ok'
    SILENCE = 'silence'
    ERROR_5XX = 'error_5xx'
    TIMEOUT = 'timeout'
    RATE_LIMITED = 'rate_limited'
    CREDIT_REFUSAL = 'credit_refusal'
    EMPTY_VALIDATED = 'empty_validated'
    INVALID_RESPONSE = 'invalid_response'
    ABANDONED = 'abandoned'
    SUPERSEDED = 'superseded'
    # Slice D (bus ask fe314f): our own failure on the attempt (invalid audio before the POST, an
    # invalid payload or unexpected local error after it). Billable, never fails over.
    LOCAL_FAILURE = 'local_failure'


class VendorHoldReason(StrEnum):
    """Why a unit is parked in ``vendor_held``: ``..._vendor_held_units{reason}``."""

    UNKNOWN = 'unknown'
    NO_HEALTHY_VENDOR = 'no_healthy_vendor'
    FUNDS_REFUSAL = 'funds_refusal'
    CAP_REACHED = 'cap_reached'
    RATE_LIMITED = 'rate_limited'
    HEALTH_UNAVAILABLE = 'health_unavailable'


class VendorHoldOutcome(StrEnum):
    """``..._vendor_held_transitions_total{outcome}``."""

    UNKNOWN = 'unknown'
    HELD = 'held'
    REDRIVEN = 'redriven'
    REROUTED_GPU = 'rerouted_gpu'
    RELEASED = 'released'


class LiveSttReason(StrEnum):
    """Live STT failover and health reasons (1:1 with the legacy LIVE_STT_REASONS frozenset)."""

    UNKNOWN = 'unknown'
    INITIALIZATION_FAILED = 'initialization_failed'
    CONNECTION_LOST = 'connection_lost'
    SEND_FAILED = 'send_failed'
    SOCKET_UNAVAILABLE = 'socket_unavailable'
    MODULATE_SERVE_ERROR = 'modulate_serve_error'
    PROVIDER_BUDGET_EXHAUSTED = 'provider_budget_exhausted'
    PROVIDER_AUTH_REJECTED = 'provider_auth_rejected'
    PROVIDER_RATE_LIMITED = 'provider_rate_limited'
    PROVIDER_429 = 'provider_429'
    PROVIDER_5XX = 'provider_5xx'
    TIMEOUT = 'timeout'
    SONIOX_IDLE_TIMEOUT = 'soniox_idle_timeout'
    SONIOX_REQUEST_TIMEOUT = 'soniox_request_timeout'
    SONIOX_NO_AUDIO_TEARDOWN = 'soniox_no_audio_teardown'
    SONIOX_ROTATION = 'soniox_rotation'
    CAPACITY_FULL = 'capacity_full'
    SEND_QUEUE_FULL = 'send_queue_full'
    REPLAY_SEND_STALLED = 'replay_send_stalled'
    DELIVERY_EXPIRED = 'delivery_expired'
    # The session's capture replay ring outgrew its horizon before the leg emitted;
    # session-local, never provider capacity or failure.
    REPLAY_RING_OVERFLOW = 'replay_ring_overflow'
    ALLOCATION_REJECTED = 'allocation_rejected'
    CAPABILITY_MISMATCH = 'capability_mismatch'
    FIRST_TEXT_DEADLINE = 'first_text_deadline'
    NO_TEXT_RESCUE_COMPLETE = 'no_text_rescue_complete'
    EMPTY_STREAK = 'empty_streak'
    SONIOX_INVALID_HINT = 'soniox_invalid_hint'
    VAD_FAILED = 'vad_failed'
    CLIENT_DISCONNECT = 'client_disconnect'
    NORMAL_CLOSE = 'normal_close'
    CANCELLED = 'cancelled'
    OTHER = 'other'
    CONFIG_INCOMPLETE = 'config_incomplete'
    AUTH = 'auth'
    QUOTA = 'quota'
    TEXT = 'text'
    NO_TEXT = 'no_text'


class LocalPreviewEngineUnavailableReason(StrEnum):
    """LivePreviewReason failure wire values; unknown client input folds to OTHER."""

    UNKNOWN = 'unknown'
    OS_TOO_OLD = 'os_too_old'
    OS_ENGINE_UNAVAILABLE = 'os_engine_unavailable'
    LOCALE_UNSUPPORTED = 'locale_unsupported'
    LOCALE_ASSET_MISSING = 'locale_asset_missing'
    SPEECH_PERMISSION_DENIED = 'speech_permission_denied'
    BUNDLED_NOT_INSTALLED = 'bundled_not_installed'
    BUNDLED_NOT_BUILT = 'bundled_not_built'
    ENGINE_ERROR = 'engine_error'
    OTHER = 'other'


class LocalPreviewOutcome(StrEnum):
    """Mobile local-preview lane admission at listen session start (routers/listen/local_preview.py)."""

    UNKNOWN = 'unknown'
    ADMITTED = 'admitted'
    NOT_REQUESTED = 'not_requested'
    KILL_SWITCH = 'kill_switch'
    CUSTOM_STT = 'custom_stt'
    MULTI_CHANNEL = 'multi_channel'
    ONBOARDING = 'onboarding'
    PHONE_CALL = 'phone_call'
    PRIVATE_SYNC_OFF = 'private_sync_off'
    NOT_BATCH_LANE = 'not_batch_lane'
    POLICY_ERROR = 'policy_error'


class ServiceWindowOutcome(StrEnum):
    """Disposition of one admitted service-VIP window POST (`utils/stt/window_replicas.py`)."""

    UNKNOWN = 'unknown'
    ERROR = 'service_error'
    QUEUE_TIMEOUT = 'service_queue_timeout'
    TEXT = 'service_text'
    EMPTY = 'service_empty'
    CANCELLED = 'service_cancelled'


class WorkerValidationStage(StrEnum):
    """Worker validation stage tokens."""

    UNKNOWN = 'unknown'
    FETCH_DECODE = 'fetch_decode'
    VAD_WINDOWS = 'vad_windows'
    WORD_CLOCKS = 'word_clocks'
    ASSEMBLE_WORDS = 'assemble_words'
    ASR_RECOVERY = 'asr_recovery'


class WorkerValidationReason(StrEnum):
    """Worker validation failure reasons."""

    UNKNOWN = 'unknown'
    STAGED_AUDIO_INVALID = 'staged_audio_invalid'
    WORD_SHAPE = 'word_shape'
    WORD_CLOCK = 'word_clock'
    WORD_SEQUENCE = 'word_sequence'
    VAD_NONFINITE = 'vad_nonfinite'
    VAD_ORDER = 'vad_order'
    VAD_BOUNDS = 'vad_bounds'
    EMPTY_ASR = 'empty_asr'
    NO_OWNED_WORDS = 'no_owned_words'
    UNSUPPORTED_LANGUAGE = 'unsupported_language'


class RecoveryFailureStage(StrEnum):
    """Recovery failure stage tokens."""

    UNKNOWN = 'unknown'
    AUDIO_VALIDATION = 'audio_validation'
    STRICT_VAD = 'strict_vad'
    PROVIDER = 'provider'
    RESPONSE_VALIDATION = 'response_validation'
    PAYLOAD_VALIDATION = 'payload_validation'


class RecoveryFailureReason(StrEnum):
    """Recovery failure reasons."""

    UNKNOWN = 'unknown'
    INVALID_AUDIO = 'invalid_audio'
    VAD_FAILED = 'vad_failed'
    INVALID_VAD = 'invalid_vad'
    NO_SPEECH = 'no_speech'
    PROVIDER_FAILED = 'provider_failed'
    INVALID_RESPONSE = 'invalid_response'
    EMPTY_ASR = 'empty_asr'
    INVALID_PAYLOAD = 'invalid_payload'
    OPERATION_FAILED = 'operation_failed'
    ABANDONED_RUNNING = 'abandoned_running'


class FallbackReason(StrEnum):
    """Every reason `record_fallback` may emit (superset of LiveSttReason)."""

    UNKNOWN = 'unknown'
    INITIALIZATION_FAILED = 'initialization_failed'
    CONNECTION_LOST = 'connection_lost'
    SEND_FAILED = 'send_failed'
    SOCKET_UNAVAILABLE = 'socket_unavailable'
    MODULATE_SERVE_ERROR = 'modulate_serve_error'
    PROVIDER_BUDGET_EXHAUSTED = 'provider_budget_exhausted'
    PROVIDER_AUTH_REJECTED = 'provider_auth_rejected'
    PROVIDER_RATE_LIMITED = 'provider_rate_limited'
    PROVIDER_429 = 'provider_429'
    PROVIDER_5XX = 'provider_5xx'
    TIMEOUT = 'timeout'
    SONIOX_IDLE_TIMEOUT = 'soniox_idle_timeout'
    SONIOX_REQUEST_TIMEOUT = 'soniox_request_timeout'
    SONIOX_NO_AUDIO_TEARDOWN = 'soniox_no_audio_teardown'
    SONIOX_ROTATION = 'soniox_rotation'
    CAPACITY_FULL = 'capacity_full'
    SEND_QUEUE_FULL = 'send_queue_full'
    REPLAY_SEND_STALLED = 'replay_send_stalled'
    DELIVERY_EXPIRED = 'delivery_expired'
    REPLAY_RING_OVERFLOW = 'replay_ring_overflow'
    ALLOCATION_REJECTED = 'allocation_rejected'
    CAPABILITY_MISMATCH = 'capability_mismatch'
    FIRST_TEXT_DEADLINE = 'first_text_deadline'
    NO_TEXT_RESCUE_COMPLETE = 'no_text_rescue_complete'
    EMPTY_STREAK = 'empty_streak'
    SONIOX_INVALID_HINT = 'soniox_invalid_hint'
    VAD_FAILED = 'vad_failed'
    CLIENT_DISCONNECT = 'client_disconnect'
    NORMAL_CLOSE = 'normal_close'
    CANCELLED = 'cancelled'
    OTHER = 'other'
    CONFIG_INCOMPLETE = 'config_incomplete'
    AUTH = 'auth'
    QUOTA = 'quota'
    TEXT = 'text'
    NO_TEXT = 'no_text'
    GATE_UNAVAILABLE = 'gate_unavailable'
    USAGE_ROOT_MISSING = 'usage_root_missing'
    USAGE_FENCE_BLOCKED = 'usage_fence_blocked'
    HTTP_ERROR = 'http_error'
    HTTP_429 = 'http_429'
    TRANSPORT_ERROR = 'transport_error'
    UNAVAILABLE = 'unavailable'
    UNCONFIGURED = 'unconfigured'
    MALFORMED = 'malformed'
    ENQUEUE_FAILED = 'enqueue_failed'
    CIRCUIT_OPEN = 'circuit_open'
    LAST_RESORT = 'last_resort'
    LOCAL_HEAL = 'local_heal'
    POLICY = 'policy'
    DISPATCH_DISABLED = 'dispatch_disabled'
    BYOK = 'byok'
    # main #22734/#22647 (sync 10)
    SESSION_EXCLUDED = 'session_excluded'
    RECOVERY_BUDGET = 'recovery_budget'
    MALFORMED_DOC = 'malformed_doc'
    AUTH_ERROR = 'auth_error'
    CONNECTION_ERROR = 'connection_error'
    PRIVATE_TOOL_OUTPUT_IN_CONTEXT = 'private_tool_output_in_context'
    NOT_AUTHORIZED = 'not_authorized'
    AUTHORIZATION_UNAVAILABLE = 'authorization_unavailable'
    UNMIGRATED_PRINCIPAL = 'unmigrated_principal'
    DOCUMENT_SIZE_LIMIT = 'document_size_limit'
    KEPT_OVER_80PCT = 'kept_over_80pct'
    NONE = 'none'
    DEFERRALS_EXHAUSTED = 'deferrals_exhausted'
    PRE_LOCK_EXPIRY = 'pre_lock_expiry'
    MARKER_CLEAR_FAILED = 'marker_clear_failed'
    MARKER_FAILED = 'marker_failed'
    OWNER_WRITE_FAILED = 'owner_write_failed'
    ENQUEUE_UNCERTAIN = 'enqueue_uncertain'
    ACQUIRE_UNSETTLED = 'acquire_unsettled'
    MARKER_TIMEOUT = 'marker_timeout'
    PREAMBLE_TIMEOUT = 'preamble_timeout'


class NotesAgentForceReason(StrEnum):
    """Why an agentic notes run was given a system-directed submit turn (first reason only)."""

    UNKNOWN = 'unknown'
    LOOKUP_CAP = 'lookup_cap'
    SUBMISSION_REJECTED_AT_CAP = 'submission_rejected_at_cap'
    SUBMISSION_REJECTED = 'submission_rejected'
    TEXT_ONLY_RESPONSE = 'text_only_response'
    PRIOR_REJECTION = 'prior_rejection'
    TURN_LIMIT = 'turn_limit'
    COST_LIMIT = 'cost_limit'
    DEADLINE = 'deadline'


class NotesAgentTransportReason(StrEnum):
    """Why a notes run could not use the managed tool transport."""

    UNKNOWN = 'unknown'
    MISSING_OWNER = 'missing_owner'
    BYOK = 'byok'
    UNSUPPORTED_MODEL = 'unsupported_model'


def reason_values(enum: type[StrEnum]) -> frozenset[str]:
    """The enum's members as plain strings, excluding ``unknown`` (legacy frozenset shape)."""
    return frozenset(member.value for member in enum if member.value != 'unknown')


def reason_label(family: ReasonFamily, value: object, enum: type[StrEnum]) -> str:
    """Return ``value`` if it is a member of ``enum``; otherwise count it and return ``'unknown'``.

    Never raises. The family label is bounded by ``ReasonFamily``.
    """
    try:
        family_label = ReasonFamily(family).value
    except Exception:
        family_label = 'unknown'
    result = 'unknown'
    try:
        if isinstance(value, str):
            result = enum(value).value
        elif isinstance(value, enum):
            result = value.value
    except Exception:
        result = 'unknown'
    try:
        OMI_REASON_TOTAL.labels(family=family_label).inc()
        if result == 'unknown' and value != 'unknown':
            REASON_UNKNOWN_TOTAL.labels(family=family_label).inc()
    except Exception:
        pass
    return result


class RecurringProfileOutcome(StrEnum):
    UNKNOWN = 'unknown'
    CREATED = 'created'
    PROMOTED = 'promoted'
    REFRESHED = 'refreshed'
    BOUND = 'bound'
    REJECTED = 'rejected'
    EXPIRED = 'expired'
    EVICTED_CAP = 'evicted_cap'


class RecurringMatchOutcome(StrEnum):
    UNKNOWN = 'unknown'
    MATCHED = 'matched'
    NEW_CANDIDATE = 'new_candidate'
    ABSTAINED_MARGIN = 'abstained_margin'
    OWNER_EXCLUDED = 'owner_excluded'
    NO_OWNER_PRINT = 'no_owner_print'
    CAP = 'cap'


class IdentitySpeechOutcome(StrEnum):
    UNKNOWN = 'unknown'
    OWNER = 'owner'
    PERSON = 'person'
    RECURRING = 'recurring'
    UNNAMED = 'unnamed'


class PipelineLedgerOutcome(StrEnum):
    UNKNOWN = 'unknown'
    OK = 'ok'
    ERROR = 'error'
    DISABLED = 'disabled'
    DUPLICATE = 'duplicate'
    STALE = 'stale'
    ILLEGAL = 'illegal'
    TERMINAL = 'terminal'


class PipelineLedgerFailureReason(StrEnum):
    UNKNOWN = 'unknown'
    TIMEOUT = 'timeout'
    UNAVAILABLE = 'unavailable'
    PERMISSION = 'permission'
    INVALID = 'invalid'
    OTHER = 'other'


class ChatResponseFailureReason(StrEnum):
    """Why a ``chat_response`` journey ended in ``failure`` (``omi_journey_failure_reason_total``).

    Mapped from the values the chat path stages in ``callback_data['error']`` by
    ``chat_response_failure_reason``. Exception class names are folded to a member
    there, so no raw class name or message text reaches a label.
    """

    UNKNOWN = 'unknown'
    IDLE_TIMEOUT = 'idle_timeout'
    SETUP_TIMEOUT = 'setup_timeout'
    TIMEOUT = 'timeout'
    PROVIDER_ERROR = 'provider_error'
    PROVIDER_REFUSAL = 'provider_refusal'
    EMPTY_ANSWER = 'empty_answer'
    STREAM_FAILURE = 'stream_failure'
    PERSISTENCE_FAILURE = 'persistence_failure'


class ListenNoAudioCloseReason(StrEnum):
    """How an accepted /v4/listen session that never sent audio was closed, as the server observed it."""

    UNKNOWN = 'unknown'
    CLIENT_CLOSE_NORMAL = 'client_close_normal'
    CLIENT_CLOSE_ABNORMAL = 'client_close_abnormal'
    SERVER_CLOSE = 'server_close'
    NO_CLOSE_FRAME = 'no_close_frame'


# Values staged on callback_data['error'] by utils.retrieval (agentic, graph) and utils.chat_turn.
_CHAT_STAGED_FAILURE_REASONS: dict[str, ChatResponseFailureReason] = {
    'idle_timeout': ChatResponseFailureReason.IDLE_TIMEOUT,
    'setup_timeout': ChatResponseFailureReason.SETUP_TIMEOUT,
    'empty_answer': ChatResponseFailureReason.EMPTY_ANSWER,
    'provider_refusal': ChatResponseFailureReason.PROVIDER_REFUSAL,
    'stream_failure': ChatResponseFailureReason.STREAM_FAILURE,
}
# Exception class names that reach callback_data['error'] as type(error).__name__.
_CHAT_EXCEPTION_FAILURE_REASONS: dict[str, ChatResponseFailureReason] = {
    'TimeoutError': ChatResponseFailureReason.TIMEOUT,
    'APITimeoutError': ChatResponseFailureReason.TIMEOUT,
    'ConnectTimeout': ChatResponseFailureReason.TIMEOUT,
    'ReadTimeout': ChatResponseFailureReason.TIMEOUT,
    'WriteTimeout': ChatResponseFailureReason.TIMEOUT,
    'PoolTimeout': ChatResponseFailureReason.TIMEOUT,
    'APIError': ChatResponseFailureReason.PROVIDER_ERROR,
    'APIStatusError': ChatResponseFailureReason.PROVIDER_ERROR,
    'APIConnectionError': ChatResponseFailureReason.PROVIDER_ERROR,
    'AuthenticationError': ChatResponseFailureReason.PROVIDER_ERROR,
    'BadRequestError': ChatResponseFailureReason.PROVIDER_ERROR,
    'InternalServerError': ChatResponseFailureReason.PROVIDER_ERROR,
    'RateLimitError': ChatResponseFailureReason.PROVIDER_ERROR,
    'ConnectError': ChatResponseFailureReason.PROVIDER_ERROR,
    'ReadError': ChatResponseFailureReason.PROVIDER_ERROR,
    'RemoteProtocolError': ChatResponseFailureReason.PROVIDER_ERROR,
    'WriteError': ChatResponseFailureReason.PROVIDER_ERROR,
}
_EXCEPTION_CLASS_NAME = re.compile(r'[A-Z][A-Za-z0-9_]{0,79}')


def chat_response_failure_reason(staged: object) -> ChatResponseFailureReason:
    """Fold a staged chat error value (sentinel or exception class name) to a member; never raises."""
    if not isinstance(staged, str):
        return ChatResponseFailureReason.UNKNOWN
    if staged in _CHAT_STAGED_FAILURE_REASONS:
        return _CHAT_STAGED_FAILURE_REASONS[staged]
    return _CHAT_EXCEPTION_FAILURE_REASONS.get(staged, ChatResponseFailureReason.UNKNOWN)


def exception_class_name(value: object) -> str | None:
    """The value when it is shaped like an exception class name, else None (no message text ever passes)."""
    if isinstance(value, str) and _EXCEPTION_CLASS_NAME.fullmatch(value):
        return value
    return None
