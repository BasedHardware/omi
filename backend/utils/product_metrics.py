"""Bounded product-event counters in the existing Prometheus registry.

Stage-1 introduced ``omi_product_event_total``. This module is that helper:
closed event vocabulary, fail-open recording, never uid / conversation / device
IDs as labels. Label names follow the repo convention (``client_kind``,
``app_build``) rather than free-text surface/version strings.

Counters are per-pod. Alert queries must ``sum()`` across
``job=backend-listen-metrics``. Zero-initialize ``event × client_kind`` only;
``app_build`` is recorded when seen and is not pre-expanded. Per-user-daily
threshold crossings zero-initialize ``event × threshold``.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from utils.account_cutover.control import parse_client_build
from utils.journey_metrics_contract import CLIENT_KINDS, resolve_client_kind_from_headers
from utils.metrics import OMI_PRODUCT_EVENT_TOTAL, OMI_PRODUCT_EVENT_USER_DAILY_OVER_TOTAL

EVENTS = frozenset(
    {
        'conversation_created',
        'conversation_finalized',
        'duplicate_capture_detected',
        'sync_job_enqueued',
        'chat_message_sent',
        'desktop_chat_completion',
        'memory_created',
        'memory_deleted',
        'memory_updated',
        'action_item_created',
        'action_item_mutated',
        'conversation_sync_mutation',
        'app_enabled',
        'conversation_deleted',
    }
)
OUTCOMES = frozenset(
    {
        'none',
        'ok',
        'error',
        'quota_exceeded',
        'applied',
        'replayed',
        'conflict',
        'success',
        'failure',
        'degraded',
        'cancelled',
        'unknown',
    }
)
SOURCES = frozenset({'none', 'client', 'import', 'extract', 'integration', 'live', 'sync', 'desktop'})
USER_DAILY_THRESHOLDS = (5, 10, 20, 50, 100, 200, 500)
OPS = frozenset(
    {
        'none',
        'update',
        'toggle_complete',
        'delete',
        'batch_delete',
        'visibility',
        'read',
        'baseline',
        'review',
        'enable',
        'disable',
    }
)
PER_USER_DAILY_EVENTS = frozenset(
    {
        'conversation_created',
        'chat_message_sent',
        'memory_created',
        'sync_job_enqueued',
    }
)
CLIENT_KIND_SET = frozenset(CLIENT_KINDS)
MAX_LABEL_LENGTH = 32
MAX_APP_BUILDS = 128
MAX_PER_USER_KEYS = 20000
_SAFE_LABEL = re.compile(r'[a-zA-Z0-9_.+-]+', re.ASCII)
_VERSION = re.compile(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,5}(?:\+[0-9]{1,10})?', re.ASCII)
_builds: set[str] = set()
_builds_lock = threading.Lock()
_per_user_counts: dict[tuple[str, str, str], int] = {}
_per_user_lock = threading.Lock()


def sanitize_label(value: object) -> str:
    """Reject rather than truncate unsafe/oversized input into plausible labels."""
    if not isinstance(value, str) or not value or len(value) > MAX_LABEL_LENGTH:
        return 'unknown'
    return value if _SAFE_LABEL.fullmatch(value) else 'unknown'


def sanitize_app_build(*raw_values: object) -> str:
    """Normalize client version headers to a bounded ``app_build`` label.

    Prefers ``parse_client_build`` (numeric Flutter ``version+build`` suffix or a
    dedicated build header). Dotted release versions that are not integers
    (desktop ``0.12.365``) stay as the sanitized version string. Anything else,
    including raw User-Agent text, collapses to ``unknown``. A process-lifetime
    cap bounds cardinality; overflow shares ``unknown``.
    """
    parsed_build: int | None = None
    version_fallback: str | None = None
    for raw in raw_values:
        if not isinstance(raw, str) or not raw:
            continue
        parsed = parse_client_build(raw)
        if parsed is not None:
            parsed_build = parsed
            break
        label = sanitize_label(raw)
        if _VERSION.fullmatch(label) and version_fallback is None:
            version_fallback = label
    if parsed_build is not None:
        candidate = str(parsed_build)
    elif version_fallback is not None:
        candidate = version_fallback
    else:
        return 'unknown'
    with _builds_lock:
        if candidate in _builds:
            return candidate
        if len(_builds) >= MAX_APP_BUILDS:
            return 'unknown'
        _builds.add(candidate)
    return candidate


def extract_app_build(request: object | None) -> str:
    """Flutter shared.dart, macOS OmiHTTPTransport, Windows apiClient use X-App-Version.

    X-App-Build is preferred when present. User-Agent is never a version source.
    """
    try:
        headers = _headers_mapping(request)
        return sanitize_app_build(headers.get('x-app-build'), headers.get('x-app-version'))
    except Exception:
        return 'unknown'


def extract_client_kind(request: object | None) -> str:
    """Closed ``CLIENT_KINDS`` value from first-party headers; never identifiers."""
    try:
        return resolve_client_kind_from_headers(_headers_mapping(request))
    except Exception:
        return 'unknown'


def _headers_mapping(request: object | None) -> dict[str, str]:
    if request is None:
        return {}
    headers = getattr(request, 'headers', request)
    if not isinstance(headers, Mapping):
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _closed(value: object, allowed: frozenset[str], default: str) -> str:
    label = sanitize_label(value) if value is not None else default
    return label if label in allowed else 'unknown' if 'unknown' in allowed else default


def _zero_initialize_label_children() -> None:
    """Export event×client_kind zeros so idle pods are distinguishable from missing scrapes.

    ``app_build`` is not pre-expanded: every historical build would multiply the
    series. Default extra labels are the unused sentinels.
    """
    for event in sorted(EVENTS):
        for client_kind in CLIENT_KINDS:
            OMI_PRODUCT_EVENT_TOTAL.labels(
                event=event,
                client_kind=client_kind,
                app_build='unknown',
                outcome='none',
                source='none',
                op='none',
            )
    for event in sorted(PER_USER_DAILY_EVENTS):
        for threshold in USER_DAILY_THRESHOLDS:
            OMI_PRODUCT_EVENT_USER_DAILY_OVER_TOTAL.labels(event=event, threshold=str(threshold))


_zero_initialize_label_children()


def observe_per_user_daily(event: str, uid: str, app_build: str | None = None, *, increment: int = 1) -> None:
    """Increment uid-free threshold counters when this process's uid-day tally crosses N.

    ``uid`` is the in-memory grouping key and is never exported. ``app_build`` is
    accepted for call-site compatibility and is not a label (threshold cardinality
    is already event × 7). Fail-open. Crossings are pod-local: sum() across pods
    counts (pod, uid-day) pairs, not globally unique users.
    """
    try:
        if not uid or increment <= 0:
            return
        event_label = _closed(event, EVENTS, 'unknown')
        if event_label not in PER_USER_DAILY_EVENTS:
            return
        _ = app_build
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        key = (event_label, uid, day)
        crossed: list[str] = []
        with _per_user_lock:
            if key not in _per_user_counts and len(_per_user_counts) >= MAX_PER_USER_KEYS:
                stale_day = min((item[2] for item in _per_user_counts), default=day)
                for stale in [item for item in _per_user_counts if item[2] <= stale_day]:
                    _per_user_counts.pop(stale, None)
            previous = _per_user_counts.get(key, 0)
            tally = previous + int(increment)
            _per_user_counts[key] = tally
            for threshold in USER_DAILY_THRESHOLDS:
                if previous < threshold <= tally:
                    crossed.append(str(threshold))
        for threshold_label in crossed:
            OMI_PRODUCT_EVENT_USER_DAILY_OVER_TOTAL.labels(event=event_label, threshold=threshold_label).inc()
    except Exception:
        return


def record_product_event(
    event: str,
    app_version: str | None = None,
    surface: str | None = None,
    *,
    client_kind: str | None = None,
    app_build: str | None = None,
    outcome: str | None = None,
    source: str | None = None,
    op: str | None = None,
    uid: str | None = None,
    request: Any = None,
    count: int = 1,
) -> None:
    """Best-effort telemetry: even label/collector failures cannot fail a request.

    ``app_version`` / ``surface`` remain accepted so the stage-1 exemplar call
    site can be migrated independently; ``surface`` is ignored (replaced by
    ``client_kind``). ``uid`` is used only for the per-user-daily threshold counter.
    """
    try:
        event_label = _closed(event, EVENTS, 'unknown')
        if request is not None:
            if client_kind is None:
                client_kind = extract_client_kind(request)
            if app_build is None and app_version is None:
                app_build = extract_app_build(request)
        kind_label = client_kind if client_kind in CLIENT_KIND_SET else 'unknown'
        build_label = sanitize_app_build(app_build, app_version)
        outcome_label = _closed(outcome, OUTCOMES, 'none') if outcome not in (None, '') else 'none'
        source_label = _closed(source, SOURCES, 'none') if source not in (None, '') else 'none'
        op_label = _closed(op, OPS, 'none') if op not in (None, '') else 'none'
        amount = max(int(count), 1)
        OMI_PRODUCT_EVENT_TOTAL.labels(
            event=event_label,
            client_kind=kind_label,
            app_build=build_label,
            outcome=outcome_label,
            source=source_label,
            op=op_label,
        ).inc(amount)
        if uid and event_label in PER_USER_DAILY_EVENTS:
            observe_per_user_daily(event_label, uid, build_label, increment=amount)
    except Exception:
        # Do not log exception text or labels: they may contain sensitive input.
        return
