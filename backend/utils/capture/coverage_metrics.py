"""Low-cardinality coverage metrics (never capture identifiers)."""

from prometheus_client import Counter

ADMIT = Counter('omi_capture_coverage_admit_total', 'Source-frame admission decisions', ['origin', 'basis', 'outcome'])
SECONDS = Counter('omi_capture_coverage_seconds_total', 'Covered audio seconds', ['origin', 'outcome'])

CROSS_DEVICE = Counter('omi_capture_coverage_cross_device_total', 'Confirmed cross-device decisions', ['outcome'])
CROSS_DEVICE_LINES = Counter(
    'omi_capture_coverage_cross_device_lines_total', 'Cross-device secondary lines examined', ['outcome']
)
