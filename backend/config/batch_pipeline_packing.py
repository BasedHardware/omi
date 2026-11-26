"""Read and cardinality limits for the lease packing observation."""

import os

DEFAULT_SAMPLE_RATE = 0.001
MAX_SAMPLE_RATE = 0.01
MAX_MEMBERS = 16
PAGE_ROWS = MAX_MEMBERS + 1
READ_TIMEOUT_SECONDS = 1.0
GAP_SECONDS = (60, 300, 3600)
PACK_SECONDS = (600, 1800, 3600)

JOB_FIELDS = (
    'segment_id',
    'capture_at',
    'duration_seconds',
    'enqueued_at',
    'available_at',
    'state',
    'priority',
    'attempt',
    'last_policy_hold',
    'packing_observation',
)


def sample_rate() -> float:
    try:
        value = float(os.getenv('BATCH_PIPELINE_PACKING_SAMPLE_RATE', str(DEFAULT_SAMPLE_RATE)))
    except ValueError:
        return DEFAULT_SAMPLE_RATE
    return value if 0.0 <= value <= MAX_SAMPLE_RATE else DEFAULT_SAMPLE_RATE
