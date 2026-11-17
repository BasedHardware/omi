"""Free-allowance watch counters, with no imports beyond prometheus_client.

The batch worker registers these on its private /metrics registry. Importing
the full watch module there would pull its lazy policy imports into the
worker's static reader closure (cross-service deploy contract), so the
counters live here and ``allowance_watch`` re-exports them.
"""

from prometheus_client import Counter

DECISIONS = Counter(
    'omi_free_allowance_watch_decisions',
    'Watch-only spend-point decisions; no user identifiers',
    ['path', 'provider', 'decision'],
)
SECONDS = Counter(
    'omi_free_allowance_watch_seconds',
    'Observed seconds by decision; requests are estimates, billing observations are separate',
    ['path', 'provider', 'decision'],
)

LEASE_DECISIONS = Counter(
    'omi_free_allowance_lease_decisions', 'Shared shadow reservation decisions; no serving effect', ['path', 'reason']
)
SETTLED_SECONDS = Counter(
    'omi_free_allowance_settled_seconds', 'Confirmed billing seconds joined to a shadow operation', ['path']
)
COLLECTORS = (DECISIONS, SECONDS, LEASE_DECISIONS, SETTLED_SECONDS)
