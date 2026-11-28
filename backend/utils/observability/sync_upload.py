"""Measure server-observed upload admission without reading bodies or changing sync."""

from prometheus_client import Counter, Histogram
from starlette.datastructures import Headers

from config.request_clock import bounded_hold_state, recovered_label
from utils.observability.fleet import record_upload
from utils.sync.capture_end import parse_trace

UPLOAD_PATHS = frozenset({'/v1/sync-local-files', '/v2/sync-local-files'})
HOLD_AGE = Histogram(
    'omi_batch_pipeline_upload_hold_age_seconds',
    'Client-reported age of the oldest sealed file when a held upload is sent',
    ['hold_state', 'recovered', 'gate'],
    buckets=(1, 5, 15, 30, 60, 120, 300, 360, 600, 900, 1200, 1800, 3600, 7200, 14400, 86400),
)
RECOVERY_LABEL_MISMATCH = Counter(
    'omi_batch_pipeline_upload_recovery_label_mismatch_total',
    'Mobile WAL uploads with missing or inconsistent recovery telemetry',
    ['direction'],
)
RECOVERY_COMPARISONS = Counter(
    'omi_batch_pipeline_upload_recovery_label_comparisons_total',
    'Mobile WAL uploads evaluated against their journal recovery state',
    ['journal_state'],
)
_JOURNAL_STATES = ('fresh', 'recovered', 'mixed')
for _direction in ('fresh_labelled_recovered', 'recovered_labelled_fresh', 'missing'):
    RECOVERY_LABEL_MISMATCH.labels(_direction)
for _state in _JOURNAL_STATES:
    RECOVERY_COMPARISONS.labels(_state)


def compare_recovery_label(journal_state: str | None, reported_recovery: str | None, hold_state: str | None) -> None:
    if journal_state is None and bounded_hold_state(hold_state) in ('none', 'unknown'):
        # Legacy and flag-off uploads may omit the fresh label.
        return
    if journal_state not in _JOURNAL_STATES:
        RECOVERY_LABEL_MISMATCH.labels('missing').inc()
        return

    RECOVERY_COMPARISONS.labels(journal_state).inc()
    if reported_recovery not in ('0', '1'):
        RECOVERY_LABEL_MISMATCH.labels('missing').inc()
    elif reported_recovery == '1' and journal_state != 'recovered':
        RECOVERY_LABEL_MISMATCH.labels('fresh_labelled_recovered').inc()
    elif reported_recovery == '0' and journal_state != 'fresh':
        RECOVERY_LABEL_MISMATCH.labels('recovered_labelled_fresh').inc()


def observe_hold_age(age_ms, hold_state, recovered, *, upload_trace, received_at):
    if not isinstance(age_ms, str) or not age_ms.isascii() or not age_ms.isdecimal():
        return
    # Bound the conversion even when the input contains leading zeroes.
    significant_digits = age_ms.lstrip('0')
    if len(significant_digits) > 8:
        return
    milliseconds = int(significant_digits or '0')
    if milliseconds <= 86_400_000:
        trace = parse_trace(upload_trace, received_at=received_at) if isinstance(upload_trace, str) else None
        gate = trace[0] if trace else 'other'
        HOLD_AGE.labels(bounded_hold_state(hold_state), recovered_label(recovered), gate).observe(milliseconds / 1000)


class SyncUploadMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or scope['path'].rstrip('/') not in UPLOAD_PATHS:
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        platform, channel = headers.get('x-app-platform'), headers.get('x-build-channel')
        record_upload('started', platform, channel)
        outcome = 'failed'

        async def measured_send(message):
            nonlocal outcome
            if message['type'] == 'http.response.start':
                status = message['status']
                outcome = (
                    'accepted'
                    if status == 202
                    else ('completed' if 200 <= status < 300 and status != 207 else 'failed')
                )
            await send(message)

        try:
            await self.app(scope, receive, measured_send)
        finally:
            record_upload(outcome, platform, channel)
