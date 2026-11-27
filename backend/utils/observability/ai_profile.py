"""Count exhausted independent AI profile refreshes without account or source labels."""

from prometheus_client import Counter

SOURCE_FENCE_RETRY_EXHAUSTED = Counter(
    'omi_ai_profile_source_fence_retry_exhausted_total',
    'Independent AI profile refreshes that exhausted the source-fence retry budget.',
)
