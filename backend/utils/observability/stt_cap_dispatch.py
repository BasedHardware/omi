"""Additive dispatch provenance, independent of root usage and unit projection."""

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
