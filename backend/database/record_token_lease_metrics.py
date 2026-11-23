"""Content-free lease telemetry shared by producers and disposable repair children."""

from prometheus_client import Counter, Gauge, Histogram

RENEWALS = Counter('omi_record_token_lease_renewals_total', 'Committed server-observed lease signals', ['source'])
SIGNAL_GAP = Histogram(
    'omi_record_token_lease_signal_gap_seconds',
    'Gap between committed token lease signals',
    buckets=(1, 5, 30, 60, 120, 300, 600, 900, 1800, 2700, 3600, 5400, 7200, 14400, 86400),
)
ACTIVE = Gauge(
    'omi_record_token_lease_active', 'Open leased tokens held by this pusher process', multiprocess_mode='livesum'
)
EXPIRED_WOULD = Counter('omi_record_token_lease_expired_would_total', 'Discovered rows blocked only by lapsed leases')
EXPIRED_SEALED = Counter(
    'omi_record_token_lease_expired_sealed_total', 'Rows released under lease proof after tail/partial gates'
)
LATE_APPEND = Counter('omi_record_token_late_append_total', 'Observed append after lease lapse or audio closure')
