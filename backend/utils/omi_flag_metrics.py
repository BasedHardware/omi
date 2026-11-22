"""Bounded server flag comparison telemetry, registered by the shared exporter."""

from prometheus_client import Counter

OMI_FLAG_DUAL_READ_TOTAL = Counter(
    'omi_flag_dual_read_total',
    'Server flag reads in OMI_FLAGS_SOURCE=dual: Omi store answer compared with the serving PostHog answer',
    ['flag', 'outcome'],
)
# Export idle zeros at startup for the bounded set of dual-read evaluator keys.
# Missing series then indicate missing runtime/scrape coverage, not no comparisons.
OMI_FLAG_DUAL_READ_TOTAL.labels(flag='proactivity_v2', outcome='match')
OMI_FLAG_DUAL_READ_TOTAL.labels(flag='proactivity_v2', outcome='mismatch')
OMI_FLAG_DUAL_READ_TOTAL.labels(flag='proactivity_v2', outcome='omi_absent')
OMI_FLAG_DUAL_READ_TOTAL.labels(flag='proactivity_v2', outcome='omi_error')
