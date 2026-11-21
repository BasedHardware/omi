"""Shared processing retry vocabulary; no provider imports on the listen path."""

PROCESSING_BURST_ATTEMPTS = 4  # Initial dispatch plus three retries.
DETERMINISTIC_PROCESSING_FAILURE = 'deterministic_processing_failed'
TRANSIENT_PROCESSING_FAILURE = 'transient_processing_failed'
