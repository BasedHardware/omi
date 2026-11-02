"""Budget contracts for the highest-cardinality Omi metric emitters.

Every series these emitters pre-create is re-created by each listen/pusher pod
and each Cloud Run instance replacement (121 listen pods and ~1,500 bridge
instances per 6h on 2026-10-21), so a label or bucket product is a standing
Prometheus-head and churn cost. These tests pin the products to what their
consumers read; extending a product here needs the consumer that reads it.
"""

from utils.metrics import CONVERSATION_DURATION_BUCKETS, JOURNEY_LATENCY_BUCKETS
from utils.observability import fallback
from utils.observability.sync_phases import CALLS, DURATION


def test_journey_latency_bucket_budget():
    # 3 journeys x 4 outcomes are pre-created per emitter; 10 finite buckets
    # keep that at 12 x 11 = 132 series instead of the 15-bucket 192.
    assert JOURNEY_LATENCY_BUCKETS == (0.5, 1, 2.5, 5, 10, 30, 60, 300, 3600, 21600)


def test_conversation_duration_bucket_budget():
    # 6 sources are pre-created per emitter for duration and speech seconds
    # each: 11 finite buckets keep that at 6 x 12 = 72 series per histogram.
    # 10 and 15 back the omi_conversation_shape contract log; 120 backs the
    # Core Features long-conversation-share panel (le="120.0").
    assert CONVERSATION_DURATION_BUCKETS == (5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600, 14400)


def _finite_buckets(histogram):
    # A labelled histogram exposes no bucket samples until a child exists.
    histogram.labels('unknown', 'gcs')
    metric = next(iter(histogram.collect()))
    les = {float(s.labels['le']) for s in metric.samples if s.name.endswith('_bucket')}
    return tuple(sorted(les - {float('inf')}))


def test_sync_phase_bucket_budget():
    assert _finite_buckets(DURATION) == (0.05, 0.5, 1, 5, 15, 60, 600)
    # le=0 isolates zero-call attempts (empty-result retries) from le=1.
    assert _finite_buckets(CALLS) == (0, 1, 4, 16, 64, 512)


def _fallback_samples():
    # The counter family collects as omi_fallback; the counter samples keep _total.
    metric = next(iter(fallback.OMI_FALLBACK_TOTAL.collect()))
    return [s for s in metric.samples if s.name == 'omi_fallback_total']


def test_fallback_zero_baseline_covers_the_alert_matrix_but_not_transcript_tokens():
    """The retired-provider alert reads the full from x to x reason product, so
    the import-time zero baseline must cover it; transcript-outcome tokens must
    stay out (they were 48 dead series per emitter)."""
    samples = _fallback_samples()
    assert samples, 'import-time zero baseline missing'
    reasons = {s.labels['reason'] for s in samples}
    assert 'text' not in reasons and 'no_text' not in reasons
    # One probe per structural leg of the alert matrix.
    labels = {tuple(sorted(s.labels.items())) for s in samples}
    for probe in (
        {
            'component': 'stt_live_session',
            'from_mode': 'soniox',
            'to_mode': 'deepgram',
            'reason': 'capacity_full',
            'outcome': 'exhausted',
        },
        {
            'component': 'stt_live_session',
            'from_mode': 'parakeet',
            'to_mode': 'unavailable',
            'reason': 'connection_lost',
            'outcome': 'exhausted',
        },
        {
            'component': 'stt_selection',
            'from_mode': 'modulate',
            'to_mode': 'unavailable',
            'reason': 'circuit_open',
            'outcome': 'exhausted',
        },
    ):
        assert tuple(sorted(probe.items())) in labels, probe
