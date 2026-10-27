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

from enum import StrEnum

from prometheus_client import Counter

REASON_VALUE_MAX_LENGTH = 40


class ReasonFamily(StrEnum):
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
    `rejected_future`/`rejected_early` are implausible stamps (bogus device
    clock marker, pre-2024 fragment) that stay refused.
    """

    UNKNOWN = 'unknown'
    ACCEPTED = 'accepted'
    ACCEPTED_FUTURE_SKEW = 'accepted_future_skew'
    REJECTED_FUTURE = 'rejected_future'
    REJECTED_EARLY = 'rejected_early'
    REJECTED_MALFORMED = 'rejected_malformed'


class WorkOutcome(StrEnum):
    """`WorkResult.outcome` tokens (`utils/batch_pipeline/contracts.py`)."""

    UNKNOWN = 'unknown'
    SUCCESS = 'success'
    SILENCE = 'silence'
    NO_RECOVERABLE_SPEECH = 'no_recoverable_speech'


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
    VAD_WINDOWS = 'vad_windows'
    WORD_CLOCKS = 'word_clocks'
    ASSEMBLE_WORDS = 'assemble_words'
    ASR_RECOVERY = 'asr_recovery'


class WorkerValidationReason(StrEnum):
    """Worker validation failure reasons."""

    UNKNOWN = 'unknown'
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
