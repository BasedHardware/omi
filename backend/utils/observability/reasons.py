"""Bounded, content-free reason vocabularies for metric labels (contract (e), backend-target-architecture).

Lane 1 owns the stub families below; lane 14 adds the migrated families (``LiveSttReason``,
``WorkerValidationReason``, ``RecoveryFailureReason``, ``ProviderSttReason``) and the label AST check.

Naming: values are ``lower_snake``, at most 40 characters, content-free; every family has
``UNKNOWN = 'unknown'``; class names end in ``Reason`` or ``Outcome``.
"""

from __future__ import annotations

from enum import StrEnum

from prometheus_client import Counter


class ReasonFamily(StrEnum):
    LIVE_STT = 'live_stt'
    WORKER_VALIDATION = 'worker_validation'
    RECOVERY_FAILURE = 'recovery_failure'
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


class RetryReason(StrEnum):
    """Expected conditions a task target answers with 409 retry (contract (d))."""

    UNKNOWN = 'unknown'
    LOCKED = 'locked'
    CALLBACK_PENDING = 'callback_pending'
    PERSISTENCE_FENCED = 'persistence_fenced'
    KILL_SWITCH_OFF = 'kill_switch_off'
    CUTOVER_STANDBY = 'cutover_standby'
    DEPENDENCY_WARMING = 'dependency_warming'
    POLICY_DEFER = 'policy_defer'


class ConsumerReason(StrEnum):
    """Why a consumed delivery ended in a non-retry outcome (contract (a))."""

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
    """Ramp-controller decision reasons (contract (g)); ``_ramp`` writes via utils/rollout/runtime_percent.py."""

    UNKNOWN = 'unknown'
    GATE_PASS = 'gate_pass'
    GATE_PENDING = 'gate_pending'
    GATE_FAIL = 'gate_fail'
    HOLD_INCOMPLETE = 'hold_incomplete'
    LOCKED_BY_OPERATOR = 'locked_by_operator'
    AT_CEILING = 'at_ceiling'
    DATA_LOSS = 'data_loss'
    PRIVACY = 'privacy'


REASON_UNKNOWN_TOTAL = Counter(
    'omi_reason_unknown_total',
    'Reason label values that were not members of their family enum (labelled unknown).',
    ['family'],
)
for _family in ReasonFamily:
    REASON_UNKNOWN_TOTAL.labels(family=_family.value)


def reason_label(family: ReasonFamily, value: object, enum: type[StrEnum]) -> str:
    """Return ``value`` if it is a member of ``enum``; otherwise count it under ``family`` and return 'unknown'.

    Never raises on a serving path.
    """
    try:
        return enum(value).value  # type: ignore[call-arg]
    except (ValueError, TypeError):
        REASON_UNKNOWN_TOTAL.labels(family=ReasonFamily(family).value).inc()
        return 'unknown'
