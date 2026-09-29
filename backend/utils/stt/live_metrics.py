"""Bounded live-chain and windowed TDT metrics, collected by the listen scrape."""

from prometheus_client import Counter, Gauge, Histogram

WINDOW_ACTIVE = Gauge('omi_stt_window_sessions_active', 'Admitted windowed TDT sessions')
WINDOW_CAP = Gauge('omi_stt_window_sessions_capacity', 'Process windowed TDT session cap')
WINDOW_ADMISSION = Counter('omi_stt_window_admissions_total', 'Window admission decisions', ['outcome'])
WINDOW_PRESSURE_REFRESH = Counter(
    'omi_stt_window_batch_pressure_refresh_total', 'Batch pressure fleet refresh outcomes', ['outcome']
)
WINDOW_PRESSURE_REFUSAL = Counter(
    'omi_stt_window_batch_pressure_refusals_total', 'Window batch pressure refusals', ['reason']
)
WINDOW_POSTS = Counter('omi_stt_window_posts_total', 'Window POST outcomes', ['outcome'])
WINDOW_LATENCY = Histogram('omi_stt_window_post_seconds', 'Window POST latency', buckets=(0.1, 0.5, 1, 2, 4, 8, 15))
WINDOW_FIRST_TEXT = Histogram(
    'omi_stt_window_first_text_seconds',
    'Wall seconds from first VAD speech sent to first nonempty windowed transcript',
    buckets=(2, 5, 10, 15, 20, 25, 30, 45, 60),
)
WINDOW_SESSION_OUTCOME = Counter(
    'omi_stt_window_session_outcome_total', 'Windowed sessions with VAD speech', ['outcome', 'reason']
)
WINDOW_REPLAY_SAFE_TRIMS = Counter(
    'omi_stt_window_replay_safe_trims_total',
    'Window replay ring overruns trimmed after all admitted speech was transcribed',
)
WINDOW_CANARY_OUTCOME = Counter(
    'omi_stt_window_canary_transcript_outcome_total',
    'Listen transcript outcome by stable window allocation arm',
    ['arm', 'outcome'],
)
WINDOW_CONTEXT = Histogram(
    'omi_stt_window_context_seconds',
    'Posted TDT context duration',
    buckets=(3, 6, 9, 12, 18, 24, 30),
)
WINDOW_FORCED_CUTS = Counter(
    'omi_stt_window_forced_cuts_total',
    'Window POSTs that hit max context without a sentence boundary',
)
WINDOW_HEAD_RECOVERIES = Counter(
    'omi_stt_window_head_recoveries_total',
    'Window POSTs whose skipped leading speech was re-posted on its own',
    ['outcome'],
)
WINDOW_DECODER_LOOPS = Counter(
    'omi_stt_window_decoder_loops_total',
    'Repeated-phrase decoder loops collapsed out of windowed TDT segments',
)
WINDOW_EMISSION_DROPS = Counter(
    'omi_stt_window_emission_drops_total',
    'Windowed TDT segments dropped instead of emitted at a fabricated position',
    ['reason'],
)
CHAIN_EXHAUSTED = Counter('omi_stt_chain_exhausted_total', 'Configured live chains that could not serve')
LEG_ATTEMPTS = Counter('omi_stt_leg_attempts_total', 'Configured-chain connection results', ['to_mode', 'outcome'])
RECONNECT = Counter(
    'omi_stt_reconnect_total', 'Bounded live STT reconnect decisions', ['provider', 'reason', 'outcome']
)
REPLAY_SECONDS = Counter('omi_stt_replay_seconds_total', 'Live STT audio replayed after reconnect', ['provider'])
LANGUAGE_CONSTRAINT = Counter(
    'omi_stt_language_constraint_total',
    'Language information sent on live STT connections',
    ['provider', 'constraint', 'primary_group', 'arm'],
)
OUTPUT_LANGUAGE_SEGMENTS = Counter(
    'omi_stt_output_language_segments_total',
    'Finalized live STT segment language conformance',
    ['provider', 'primary_group', 'arm', 'conformance', 'profile_source'],
)
LEG_TRANSCRIPT_OUTCOME = Counter(
    'omi_stt_leg_transcript_outcome_total',
    'Provider leg outcome after VAD speech; text must arrive within the configured deadline',
    ['provider', 'language', 'outcome'],
)
ROUTING_DECISION = Counter('omi_stt_routing_decisions_total', 'Health-weighted routing decisions', ['outcome'])
FLEET_HEALTH_WRITE_DROPPED = Counter(
    'omi_stt_fleet_health_write_dropped_total',
    'Fleet outcome Redis writes dropped when the bounded background slots are full or unavailable',
    ['kind'],
)
ROUTING_DECISION_LATENCY = Histogram(
    'omi_stt_routing_decision_seconds',
    'Time spent choosing the eligible live STT order without network operations',
    buckets=(0.0001, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.05),
)
