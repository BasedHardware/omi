"""Error-class sentinel sweep: detect new or surging ERROR+ classes in prod.

Every 15 minutes Cloud Scheduler POSTs the sweep route. The sweep reads the
trailing hour of ERROR+ Cloud Logging entries for the transcription fleet
(backend, backend-sync, backend-sync-backfill, backend-integration,
backend-listen, and the prod-omi-gke batch/pusher/listen pods), fingerprints
each entry into an error class, compares hourly counts against a 7-day Redis
baseline, and bumps the firing counter for classes that are new (>= 20/h) or
surging (>= 50/h and >= 5x their span-decayed baseline mean). The Grafana rule
``omi-error-class-firing`` pages on that counter's increase; the firing gauge
is display-only, and ``omi-error-class-sweep-silent`` is the dead-man.

Why a scheduled job and not a log-based metric: a fingerprint needs multi-line
traceback stitching and id-normalized message templates, which log-metric label
extractors (single-entry regexes) cannot express. Loki log alerting was retired
(LOG_CONSOLIDATION.md) and every Monitoring-policy provisioning entry point is
workflow-owned under ``.github/``, so the detector ships as this sweep - the
same shape as the other backend-sync scheduler sweeps.

Container stderr arrives as severity=ERROR regardless of app level, so app
levels are parsed from the message: WARNING classes alert at doubled
thresholds, INFO never alerts. Every failure mode fails closed: a read error,
permission denial, or truncation suppresses alerting for that tick and reports
it through the sweep counter. Fingerprints and counts only - this module never
logs or stores raw entry payloads.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import google.auth
from google.auth.transport.requests import AuthorizedSession

from database import error_class_baseline as baseline_db
from utils.error_class_fingerprint import fingerprint_entry, stitch_tracebacks
from utils.executors import db_executor, run_blocking
from utils.metrics import OMI_ERROR_CLASS_ALERT_FIRED_TOTAL, OMI_ERROR_CLASS_ALERT_FIRING, OMI_ERROR_CLASS_SWEEP_TOTAL

logger = logging.getLogger(__name__)

PROJECT_ID = 'based-hardware'
LOGGING_ENTRIES_LIST_URL = 'https://logging.googleapis.com/v2/entries:list'
LOGGING_READ_SCOPE = 'https://www.googleapis.com/auth/logging.read'
LOG_PAGE_SIZE = 1000
LOG_MAX_PER_PASS = 60_000
LOG_REQUEST_TIMEOUT_SECONDS = 30

# The Cloud Logging view trails live by ~20 minutes; a window touching "now"
# undercounts by the unmaterialized tail, so the measured hour ends 20 min ago.
VIEW_LAG = timedelta(minutes=20)
WINDOW = timedelta(hours=1)

NEW_THRESH = 20
SURGE_THRESH = 50
SURGE_MULT = 5

SCOPE = (
    '((resource.type="cloud_run_revision" AND (resource.labels.service_name="backend"'
    ' OR resource.labels.service_name="backend-sync" OR resource.labels.service_name="backend-integration"'
    ' OR resource.labels.service_name="backend-sync-backfill" OR resource.labels.service_name="backend-listen"))'
    ' OR (resource.type="k8s_container" AND resource.labels.cluster_name="prod-omi-gke" AND'
    ' (resource.labels.pod_name:"batch-pipeline-worker" OR resource.labels.pod_name:"pusher"'
    ' OR resource.labels.pod_name:"backend-listen")))'
)
# One stderr warning storm can exceed the page budget alone; splitting the read
# keeps it from truncating the alert-relevant ERROR/exception set.
EXCL_CHATTY = ' AND NOT textPayload=~"^(WARNING|INFO|DEBUG)"'
ONLY_WARNING = ' AND textPayload=~"^WARNING"'

_firing_labels: set[tuple[str, str]] = set()


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def window_bounds(now: datetime) -> tuple[datetime, datetime]:
    end = now - VIEW_LAG
    return end - WINDOW, end


def log_filter(start: datetime, end: datetime, extra: str = '') -> str:
    return 'severity>=ERROR AND timestamp>="%s" AND timestamp<="%s" AND %s%s' % (
        _iso_z(start),
        _iso_z(end),
        SCOPE,
        extra,
    )


def read_log_entries(
    *,
    start: datetime,
    end: datetime,
    extra: str = '',
    session: Any = None,
    max_entries: int = LOG_MAX_PER_PASS,
) -> dict[str, Any]:
    """One bounded paged read; ``{'entries', 'truncated', 'errors', 'status'}``."""
    if session is None:
        credentials, _ = google.auth.default(scopes=[LOGGING_READ_SCOPE])
        session = AuthorizedSession(credentials)
    entries: list[dict] = []
    token = ''
    truncated = False
    status = 200
    while True:
        body = {
            'resourceNames': ['projects/%s' % PROJECT_ID],
            'filter': log_filter(start, end, extra),
            'orderBy': 'timestamp asc',
            'pageSize': LOG_PAGE_SIZE,
            'pageToken': token,
        }
        try:
            response = session.post(LOGGING_ENTRIES_LIST_URL, json=body, timeout=LOG_REQUEST_TIMEOUT_SECONDS)
            status = response.status_code
            if status != 200:
                logger.error('error_class_sentinel log read failed status=%s', status)
                return {'entries': entries, 'truncated': truncated, 'errors': 1, 'status': status}
            payload = response.json()
        except Exception as error:  # transport failures fail the tick closed
            logger.error('error_class_sentinel log read failed type=%s', type(error).__name__)
            return {'entries': entries, 'truncated': truncated, 'errors': 1, 'status': 0}
        entries.extend(payload.get('entries') or [])
        token = payload.get('nextPageToken') or ''
        if len(entries) >= max_entries:
            truncated = bool(token)
            break
        if not token:
            break
    return {'entries': entries[:max_entries], 'truncated': truncated, 'errors': 0, 'status': status}


def _bucket_of(timestamp: str | None, fallback_epoch_hour: int) -> int:
    if timestamp:
        try:
            return int(datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp()) // 3600
        except ValueError:
            pass
    return fallback_epoch_hour


def evaluate_window(
    entries: list[dict],
    *,
    now_epoch: int,
    client: Any,
) -> dict[str, Any]:
    """Fingerprint, baseline, and classify one window's entries (sync)."""
    stitched = stitch_tracebacks(entries)
    current_bucket = now_epoch // 3600
    # Buckets from the window under evaluation must not dilute its own baseline.
    window_start_bucket = (now_epoch - int((WINDOW + VIEW_LAG).total_seconds())) // 3600
    counts: Counter = Counter()
    labels: dict[str, str] = {}
    levels: dict[str, str] = {}
    services: dict[str, str] = {}
    buckets: dict[str, Counter] = {}
    for entry in stitched:
        fp = fingerprint_entry(entry)
        resource_labels = (entry.get('resource') or {}).get('labels') or {}
        service = resource_labels.get('service_name') or resource_labels.get('container_name') or '?'
        counts[fp.fingerprint] += 1
        labels[fp.fingerprint] = fp.label
        levels[fp.fingerprint] = fp.level
        services.setdefault(fp.fingerprint, service)
        bucket = _bucket_of(entry.get('timestamp'), current_bucket)
        buckets.setdefault(fp.fingerprint, Counter())[bucket] += 1

    fired: list[dict[str, Any]] = []
    for fp, count in counts.most_common():
        record = baseline_db.record_window(
            client,
            fingerprint=fp,
            label=labels[fp],
            level=levels[fp],
            window_buckets=dict(buckets[fp]),
            now_epoch=now_epoch,
        )
        mean = baseline_db.baseline_mean(client, fp, before_bucket=window_start_bucket, record=record)
        first_seen = baseline_db.first_seen_epoch(client, fp, record=record) or now_epoch
        threshold_new, threshold_surge = _thresholds(levels[fp])
        disposition = 'ok'
        # "New" keys on absent baseline, not on record age: a class that first
        # appears below the new threshold and then crosses it still has no
        # prior buckets, so it must alert on the later sweep.
        if mean is None and count >= threshold_new:
            disposition = 'new'
        elif mean is not None and count >= threshold_surge and count >= SURGE_MULT * mean:
            disposition = 'surge'
        if disposition in ('new', 'surge') and not baseline_db.recently_alerted(client, fp):
            baseline_db.mark_alerted(client, fp, now_epoch=now_epoch)
            fired.append(
                {
                    'fingerprint': fp,
                    'label': labels[fp],
                    'count': count,
                    'baseline_mean': round(mean, 2) if mean is not None else None,
                    'disposition': disposition,
                    'service': services[fp],
                    'first_seen': first_seen,
                }
            )
    fire_alerts(fired)
    return {'classes': len(counts), 'fired': fired}


def _thresholds(level: str) -> tuple[int, int]:
    if level == 'WARNING':
        # Doubled for warning-level classes (exceptions included): container
        # stderr is severity=ERROR at the Cloud Logging level regardless.
        return 2 * NEW_THRESH, 2 * SURGE_THRESH
    if level in ('INFO', 'DEBUG'):
        return 10**9, 10**9
    # ERROR, CRITICAL, and unknown ('?' - bare tracebacks, request-log 5xx)
    # all alert at the standard thresholds.
    return NEW_THRESH, SURGE_THRESH


def fire_alerts(fired: list[dict[str, Any]]) -> int:
    """Count the firing signal, raise the display gauge, log one line per class.

    The alert rule keys on the monotonic fired counter: a gauge held at 1 by an
    instance that stops running sweeps would page forever, while a frozen
    counter's increase decays to zero within the rule window.
    """
    global _firing_labels
    active: set[tuple[str, str]] = set()
    for alert in fired:
        OMI_ERROR_CLASS_ALERT_FIRED_TOTAL.labels(fingerprint=alert['fingerprint'], service=alert['service']).inc()
        OMI_ERROR_CLASS_ALERT_FIRING.labels(fingerprint=alert['fingerprint'], service=alert['service']).set(1)
        active.add((alert['fingerprint'], alert['service']))
        logger.error(
            'error_class_alert disposition=%s count_per_h=%d baseline_mean=%s service=%s first_seen_epoch=%d class=%s',
            alert['disposition'],
            alert['count'],
            alert['baseline_mean'],
            alert['service'],
            alert['first_seen'],
            alert['label'],
        )
    for fingerprint, service in _firing_labels - active:
        OMI_ERROR_CLASS_ALERT_FIRING.labels(fingerprint=fingerprint, service=service).set(0)
    _firing_labels = active
    return len(fired)


def _tick(
    client_factory: Callable[[], Any] = baseline_db.baseline_client,
    session_factory: Callable[[], Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    start, end = window_bounds(now)
    now_epoch = int(now.timestamp())
    session = session_factory() if session_factory else None
    passes = [
        read_log_entries(start=start, end=end, extra=extra, session=session) for extra in (EXCL_CHATTY, ONLY_WARNING)
    ]
    outcome = 'ok'
    if any(p['errors'] for p in passes):
        outcome = 'permission_denied' if any(p['status'] == 403 for p in passes) else 'error'
    elif any(p['truncated'] for p in passes):
        outcome = 'truncated'
    entries = [entry for p in passes for entry in p['entries']]
    summary: dict[str, Any] = {'outcome': outcome, 'entries': len(entries)}
    if outcome != 'ok':
        # Fail closed: unbounded or unreadable counts must not raise alerts.
        OMI_ERROR_CLASS_SWEEP_TOTAL.labels(outcome=outcome).inc()
        logger.warning('error_class_sentinel sweep outcome=%s entries=%d', outcome, len(entries))
        return summary
    client = client_factory()
    result = evaluate_window(entries, now_epoch=now_epoch, client=client)
    OMI_ERROR_CLASS_SWEEP_TOTAL.labels(outcome='ok').inc()
    summary.update({'classes': result['classes'], 'fired': len(result['fired'])})
    return summary


async def run_error_class_sweep() -> dict[str, Any]:
    """Scheduler entrypoint; blocking work runs on the db executor."""
    return await run_blocking(db_executor, _tick)
