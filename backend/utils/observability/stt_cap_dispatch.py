"""Additive dispatch provenance, independent of root usage and unit projection."""

from prometheus_client import Counter

AUDIO_SECONDS = Counter(
    'omi_stt_cap_provider_audio_seconds',
    'Provider-accepted or cap-suppressed audio; never the legacy monthly usage counter',
    ['path', 'outcome', 'provider', 'allowance'],
)
CONFIG_ERRORS = Counter('omi_stt_cap_launch_config_errors', 'Invalid subscription launch configuration', ['reason'])


def record_audio(path, outcome, provider, seconds, exhausted=False):
    provider = getattr(provider, 'value', provider)
    provider = provider if provider in {'deepgram', 'modulate', 'soniox', 'parakeet'} else 'unknown'
    if seconds > 0:
        AUDIO_SECONDS.labels(path, outcome, provider, 'exhausted' if exhausted else 'other').inc(seconds)
