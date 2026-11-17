"""Import-light retirement telemetry, exported even with mirror/driver disabled."""

from enum import StrEnum
import time

from prometheus_client import Counter, Gauge

from database.reason_labels import ReasonFamily, reason_label


class RetirementPageReason(StrEnum):
    UNKNOWN = 'unknown'
    SCHEMA_MISSING = 'schema_missing'
    OPERATION_FAILED = 'operation_failed'
    TIMEOUT = 'timeout'
    INVALID_CONFIG = 'invalid_config'


_LABELS = ['namespace', 'source', 'table']
ROWS_RETIRED = Counter('omi_jobstore_retirement_rows_total', 'Committed copy retirements.', _LABELS)
PAGE_ERRORS = Counter(
    'omi_jobstore_retirement_page_errors_total', 'Failed/skipped rotation pages.', [*_LABELS, 'reason']
)
ROTATION_COMPLETED = Gauge(
    'omi_jobstore_retirement_rotation_completed_timestamp_seconds',
    'Last committed pass completion from the cursor row; zero before the first pass.',
    _LABELS,
)
ROTATION_LAG = Gauge(
    'omi_jobstore_retirement_rotation_lag_seconds',
    'Age of cursor last completed pass, or cursor creation before the first pass; not row age.',
    _LABELS,
)
RETIREMENT_COLLECTORS = (ROWS_RETIRED, PAGE_ERRORS, ROTATION_COMPLETED, ROTATION_LAG)


def page_error(namespace: str, source: str, table: str, reason: RetirementPageReason) -> None:
    PAGE_ERRORS.labels(
        namespace=namespace,
        source=source,
        table=table,
        reason=reason_label(ReasonFamily.PARITY, reason, RetirementPageReason),
    ).inc()


def observe(namespace: str, source: str, table: str, deleted: int, timestamps: tuple) -> None:
    created, completed, _updated = timestamps
    ROWS_RETIRED.labels(namespace=namespace, source=source, table=table).inc(deleted)
    ROTATION_COMPLETED.labels(namespace=namespace, source=source, table=table).set(
        completed.timestamp() if completed else 0
    )
    baseline = (completed or created).timestamp()
    # This grows between ticks (including failed ticks). No SQL on scrape.
    ROTATION_LAG.labels(namespace=namespace, source=source, table=table).set_function(
        lambda: max(0.0, time.time() - baseline)
    )
