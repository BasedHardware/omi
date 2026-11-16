"""Sample observations, including retries; never receipts or permanent-loss estimates."""

from prometheus_client import Counter

SAMPLES = Counter('omi_audio_relay_samples_total', 'Relay sample observations including retries', ['stage'])
for _stage in ('sent', 'committed', 'recovered', 'missing'):
    SAMPLES.labels(stage=_stage)
