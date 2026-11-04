"""Bounded attempt-local People scan eligibility and reuse, without identities."""

from prometheus_client import Counter

PEOPLE_SCAN_TOTAL = Counter(
    'omi_people_scan_dedupe_total',
    'People memo candidates: first/repeat key before ramp; hit/scan when enabled',
    ['site', 'outcome'],
)
PEOPLE_SCAN_SITES = frozenset({'known_spellings', 'name_fallback', 'sync_context', 'other'})
