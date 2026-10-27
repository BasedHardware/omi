"""Additive dispatch provenance, independent of root usage and unit projection."""

from enum import StrEnum

from prometheus_client import Counter, Gauge
from config.stt_cap_dispatch import execution_admission_configured as enabled
from config.stt_cap_dispatch import recovery_cohort_state
import logging

AUDIO_SECONDS = Counter(
    'omi_stt_cap_provider_audio_seconds',
    'Provider-accepted or cap-suppressed audio; never the legacy monthly usage counter',
    ['path', 'outcome', 'provider', 'allowance'],
)
CONFIG_ERRORS = Counter('omi_stt_cap_launch_config_errors', 'Invalid subscription launch configuration', ['reason'])
RECONCILIATION = Counter('omi_stt_cap_recovery_reconciliation', 'Held piece reconciliation transitions', ['outcome'])
COHORT_SOURCE = Gauge('omi_stt_cap_cohort_source', 'Active cohort source (one hot)', ['source'])
COHORT_PERCENT = Gauge('omi_stt_cap_cohort_percent', 'Active percentage; explicit UID members are not represented')
COHORT_REFRESH_FAILURES = Counter('omi_stt_cap_cohort_refresh_failures', 'Cohort refresh failures', ['reason'])
RECOVERY_COHORT_NARROWED = Gauge(
    'omi_stt_cap_recovery_cohort_narrowed', 'Recovery-only cohort configuration (one hot)', ['state']
)
for _state in ('unset', 'set', 'malformed'):
    RECOVERY_COHORT_NARROWED.labels(state=_state).set_function(
        lambda state=_state: int(recovery_cohort_state() == state)
    )
logger = logging.getLogger(__name__)


def record_reconciliation(outcome: str, hold_id: str, piece: str) -> None:
    if not enabled():
        return
    if outcome not in {'cleared_noncall', 'reconciled_ingested', 'redispatched', 'failed', 'settled_empty'}:
        raise ValueError('unknown reconciliation outcome')
    RECONCILIATION.labels(outcome=outcome).inc()
    logger.info('event=stt_cap_recovery_reconciliation outcome=%s hold_id=%s piece=%r', outcome, hold_id, piece)


def record_audio(path, outcome, provider, seconds, exhausted=False):
    provider = getattr(provider, 'value', provider)
    provider = provider if provider in {'deepgram', 'modulate', 'soniox', 'parakeet'} else 'unknown'
    if seconds > 0:
        AUDIO_SECONDS.labels(path, outcome, provider, 'exhausted' if exhausted else 'other').inc(seconds)


class DispatchPath(StrEnum):
    SYNC_V1 = 'sync_v1'
    SYNC_V2 = 'sync_v2'
    SYNC_SEGMENT = 'sync_segment'
    LANGUAGE_PROBE = 'sync_language_probe'
    EMPTY_RETRY = 'sync_empty_retry'
    MULTILINGUAL = 'sync_multilingual'
    BATCH_GPU = 'batch_gpu'
    BATCH_PROVIDER = 'batch_provider'
    SPEECH_REDRIVE = 'batch_speech_redrive'
    QUARANTINE = 'batch_quarantine'


class DispatchReason(StrEnum):
    SCOPE_DISABLED = 'scope_disabled'
    CONSENT_DENIED = 'consent_denied'
    ALLOWANCE_EXHAUSTED = 'allowance_exhausted'
    BUDGET_EXHAUSTED = 'budget_exhausted'
    ALLOWANCE_UNAVAILABLE = 'allowance_unavailable'
    ACCESS_DENIED = 'access_denied'
    ENTITLED = 'entitled'
    BYOK = 'byok'


DISPATCH_DECISIONS = Counter(
    'omi_stt_cap_dispatch_decisions',
    'Allowance decisions before offline provider spend; bounded labels, no account identifiers',
    ['path', 'outcome', 'reason'],
)


def record_decision(path: DispatchPath, allowed: bool, reason: DispatchReason) -> bool:
    # Enforce closed enums at the emitter; never label raw policy/error strings.
    DISPATCH_DECISIONS.labels(
        DispatchPath(path).value, 'allowed' if allowed else 'held', DispatchReason(reason).value
    ).inc()
    return allowed


def allowance_decision_reason(allowance) -> DispatchReason:
    return (
        DispatchReason.ENTITLED
        if allowance.managed
        else {
            'plan_allowance_exhausted': DispatchReason.ALLOWANCE_EXHAUSTED,
            'usage_budget_exhausted': DispatchReason.BUDGET_EXHAUSTED,
            'allowance_unavailable': DispatchReason.ALLOWANCE_UNAVAILABLE,
            'usage_invalid': DispatchReason.ALLOWANCE_UNAVAILABLE,
        }.get(allowance.reason, DispatchReason.ACCESS_DENIED)
    )


def record_allowance_decision(path: DispatchPath, allowance) -> bool:
    return record_decision(path, allowance.managed, allowance_decision_reason(allowance))
