"""Additive dispatch provenance, independent of root usage and unit projection."""

from prometheus_client import Counter
from config.stt_cap_dispatch import enabled
import logging

AUDIO_SECONDS = Counter(
    'omi_stt_cap_provider_audio_seconds',
    'Provider-accepted or cap-suppressed audio; never the legacy monthly usage counter',
    ['path', 'outcome', 'provider', 'allowance'],
)
CONFIG_ERRORS = Counter('omi_stt_cap_launch_config_errors', 'Invalid subscription launch configuration', ['reason'])
RECONCILIATION = Counter('omi_stt_cap_recovery_reconciliation', 'Held piece reconciliation transitions', ['outcome'])
logger = logging.getLogger(__name__)


def record_reconciliation(outcome: str, hold_id: str, piece: str) -> None:
    if not enabled():
        return
    if outcome not in {'cleared_noncall', 'reconciled_ingested', 'redispatched', 'failed'}:
        raise ValueError('unknown reconciliation outcome')
    RECONCILIATION.labels(outcome=outcome).inc()
    logger.info('event=stt_cap_recovery_reconciliation outcome=%s hold_id=%s piece=%r', outcome, hold_id, piece)


def record_audio(path, outcome, provider, seconds, exhausted=False):
    provider = getattr(provider, 'value', provider)
    provider = provider if provider in {'deepgram', 'modulate', 'soniox', 'parakeet'} else 'unknown'
    if seconds > 0:
        AUDIO_SECONDS.labels(path, outcome, provider, 'exhausted' if exhausted else 'other').inc(seconds)
