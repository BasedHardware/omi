"""Bounded live-chain and windowed TDT metrics, collected by the listen scrape."""

from prometheus_client import Counter, Gauge, Histogram

WINDOW_ACTIVE = Gauge('omi_stt_window_sessions_active', 'Admitted windowed TDT sessions')
WINDOW_CAP = Gauge('omi_stt_window_sessions_capacity', 'Process windowed TDT session cap')
WINDOW_ADMISSION = Counter('omi_stt_window_admissions_total', 'Window admission decisions', ['outcome'])
WINDOW_POSTS = Counter('omi_stt_window_posts_total', 'Window POST outcomes', ['outcome'])
WINDOW_LATENCY = Histogram('omi_stt_window_post_seconds', 'Window POST latency', buckets=(0.1, 0.5, 1, 2, 4, 8, 15))
WINDOW_CONTEXT = Histogram(
    'omi_stt_window_context_seconds',
    'Posted TDT context duration',
    buckets=(3, 6, 9, 12, 18, 24, 30),
)
WINDOW_FORCED_CUTS = Counter(
    'omi_stt_window_forced_cuts_total',
    'Window POSTs that hit max context without a sentence boundary',
)
CHAIN_EXHAUSTED = Counter('omi_stt_chain_exhausted_total', 'Configured live chains that could not serve')
LEG_ATTEMPTS = Counter('omi_stt_leg_attempts_total', 'Configured-chain connection results', ['to_mode', 'outcome'])
