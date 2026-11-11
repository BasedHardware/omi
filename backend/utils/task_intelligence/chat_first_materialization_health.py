"""Read-only health reporting for Chat-first proactive materialization."""

from __future__ import annotations

import collections
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Iterator, List, Literal, TypedDict, cast

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.chat_first_intents import DEAD_LETTERS_COLLECTION, INTENTS_COLLECTION

DEFAULT_STALE_AFTER_HOURS = 48
SCHEDULED_WEEKDAY_UTC = 0  # Monday
SCHEDULED_HOUR_UTC = 14
# The scheduled check runs weekly; a 14-day window is two report cycles. That
# gives every intent that goes stale at least one full cycle in which a run is
# guaranteed to see it (a 7-day window flush against a 7-day cadence would clip
# documents at the boundary under any clock skew), plus a second cycle so a
# genuinely-resolved problem is confirmed clear rather than blinking healthy
# for exactly one week before the same class of drop reappears. It is also
# comfortably longer than DEFAULT_STALE_AFTER_HOURS (48h): every intent inside
# the window has already had its full staleness period to be decided, so
# windowing never truncates an intent's chance to mature from in-flight to
# dropped.
HEALTH_CHECK_WINDOW_DAYS = 14
HEALTH_LOG_MARKER = 'chat_first_materialization_health'
DELIVERED = 'delivered'

logger = logging.getLogger(__name__)


class MaterializationHealthReport(TypedDict):
    scope: str
    stale_after_hours: int
    window_start: str | None
    delivered: int
    dropped: int
    in_flight: int
    undated: int
    decided: int
    drop_rate: float | None
    dropped_by_source: Dict[str, int]
    delivered_by_source: Dict[str, int]
    dropped_by_block_type: Dict[str, int]


MaterializationHealthStatus = Literal['not_due', 'healthy', 'unhealthy', 'monitor_error']
MaterializationHealthCollector = Callable[
    [str | None, int | None, int, datetime, datetime | None], MaterializationHealthReport
]


def _documents(
    uid: str | None,
    limit: int | None,
    min_created_at: datetime | None,
    *,
    firestore_client: Any = None,
) -> Iterator[Dict[str, Any]]:
    """Stream intent documents without requiring a composite Firestore index.

    ``min_created_at``, when given, adds one ``created_at >=`` inequality
    filter. A lone filter on a single field needs no explicit index -- it is
    served by Firestore's automatic per-field index -- so this stays index-free
    exactly like ``llm_usage.get_global_top_features``'s
    ``collection_group("llm_usage").where("date", ">=", cutoff_id)``, the
    existing precedent for a single-field range filter on a collection-group
    query in this codebase. A *composite* (multi-field or field+order) shape
    would need a registered index (see database/firestore_index_registry.py);
    this query never grows past one filter, so it never needs one.

    The filter also bounds the read itself: unfiltered, this was scanning
    every intent ever written, with cost climbing in lockstep with the
    collection's all-time size regardless of how much of it was recent.

    Trade-off: Firestore excludes a document from a field filter's results
    when that document is missing the field or holds a value of a different
    type, independent of when the document was written. So a windowed scan
    can never see a document with a missing or malformed ``created_at`` --
    not "only an old one," but none, ever, no matter how fresh. That is an
    acceptable gap here because ``ProactiveIntent.created_at`` is a required
    field (models/chat_first.py), so a document missing it already bypassed
    the normal write path; auditing for that class of corruption is what the
    CLI's unwindowed run (``min_created_at=None``) is for.
    """

    client = firestore_client or get_firestore_client()
    remaining = limit
    for collection_name in (INTENTS_COLLECTION, DEAD_LETTERS_COLLECTION):
        if uid:
            query: Any = client.collection('users').document(uid).collection(collection_name)
        else:
            query = client.collection_group(collection_name)
        if min_created_at is not None:
            query = query.where(filter=FieldFilter('created_at', '>=', min_created_at))
        if remaining is not None:
            query = query.limit(remaining)
        for snapshot in query.stream():
            raw: object = snapshot.to_dict()
            if isinstance(raw, dict):
                yield cast(Dict[str, Any], raw)
                if remaining is not None:
                    remaining -= 1
                    if remaining == 0:
                        return


def _created_at(document: Dict[str, Any]) -> datetime | None:
    value = document.get('created_at')
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _block_types(document: Dict[str, Any]) -> List[str]:
    blocks = document.get('blocks')
    if not isinstance(blocks, list):
        return []
    types: List[str] = []
    for block in cast(List[Any], blocks):
        if isinstance(block, dict):
            block_type = cast(Dict[str, Any], block).get('type')
            if isinstance(block_type, str):
                types.append(block_type)
    return types


def summarize(
    documents: Iterable[Dict[str, Any]],
    *,
    scope: str,
    stale_after_hours: int,
    now: datetime,
    window_start: datetime | None = None,
) -> MaterializationHealthReport:
    """Bucket intent documents into delivered, dropped, in-flight, and malformed.

    ``window_start`` is recorded on the report only -- it does not filter
    ``documents`` here. The caller (``collect``) is responsible for having
    already bounded the scan; this function just describes what period the
    counts below cover, so a windowed and an all-time report never look alike
    by accident.
    """

    cutoff = now - timedelta(hours=stale_after_hours)
    delivered = 0
    in_flight = 0
    undated = 0
    dropped_by_source: collections.Counter[str] = collections.Counter()
    dropped_by_block: collections.Counter[str] = collections.Counter()
    delivered_by_source: collections.Counter[str] = collections.Counter()

    for document in documents:
        source = str(document.get('source') or 'unknown')
        if document.get('delivery_state') == DELIVERED:
            delivered += 1
            delivered_by_source[source] += 1
            continue
        created_at = _created_at(document)
        if created_at is None:
            # Never silently fold a malformed record into either outcome.
            undated += 1
            continue
        if created_at > cutoff:
            in_flight += 1
            continue
        dropped_by_source[source] += 1
        for block_type in set(_block_types(document)):
            dropped_by_block[block_type] += 1

    dropped = sum(dropped_by_source.values())
    decided = dropped + delivered
    return {
        'scope': scope,
        'stale_after_hours': stale_after_hours,
        'window_start': window_start.isoformat() if window_start is not None else None,
        'delivered': delivered,
        'dropped': dropped,
        'in_flight': in_flight,
        'undated': undated,
        'decided': decided,
        'drop_rate': (dropped / decided) if decided else None,
        'dropped_by_source': dict(dropped_by_source.most_common()),
        'delivered_by_source': dict(delivered_by_source.most_common()),
        'dropped_by_block_type': dict(dropped_by_block.most_common()),
    }


def collect(
    uid: str | None,
    limit: int | None,
    stale_after_hours: int,
    now: datetime,
    min_created_at: datetime | None = None,
    *,
    firestore_client: Any = None,
) -> MaterializationHealthReport:
    return summarize(
        _documents(uid, limit, min_created_at, firestore_client=firestore_client),
        scope=uid or 'all_accounts',
        stale_after_hours=stale_after_hours,
        now=now,
        window_start=min_created_at,
    )


def render(report: MaterializationHealthReport) -> str:
    rate = report['drop_rate']
    window_start = report['window_start']
    window_desc = 'all-time' if window_start is None else f'since {window_start}'
    lines = [
        f"scope                {report['scope']}",
        f"window               {window_desc}",
        f"stale after          {report['stale_after_hours']}h",
        f"delivered            {report['delivered']}",
        f"dropped              {report['dropped']}",
        f"still in flight      {report['in_flight']} (excluded from the rate)",
        f"drop rate            {'n/a (no decided intents)' if rate is None else f'{rate:.2%}'}",
    ]
    if report['undated']:
        lines.append(f"undated records      {report['undated']} (no created_at; not counted either way)")
    for label, key in (('dropped by source', 'dropped_by_source'), ('dropped by block type', 'dropped_by_block_type')):
        values = report[key]
        if values:
            lines.append(f'{label}:')
            lines.extend(f'  {name:<24} {count}' for name, count in values.items())
    return '\n'.join(lines)


def is_scheduled_time(now: datetime) -> bool:
    normalized = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    return normalized.weekday() == SCHEDULED_WEEKDAY_UTC and normalized.hour == SCHEDULED_HOUR_UTC


def run_scheduled_check(
    now: datetime | None = None,
    *,
    collector: MaterializationHealthCollector = collect,
) -> MaterializationHealthStatus:
    """Emit one bounded weekly verdict for the routed decision-review signal.

    Any durable drop is actionable: the stale-age boundary has already removed
    in-flight intents, so a non-zero result is evidence that the single-client
    materializer lost a card. Malformed undated rows alarm too because they make
    the rate unknowable. A healthy verdict is routed too: the purpose of this
    check is to force the deferred server-materialization decision, and silence
    must not let a clean result drift into "never." The log intentionally carries
    aggregate counts only; source labels and block payloads stay in the explicit
    operator CLI output.

    The scan is windowed to the last HEALTH_CHECK_WINDOW_DAYS: an all-time scan
    both grows its own read cost forever and, because nothing ever deletes an
    intent document, latches this verdict unhealthy permanently after the first
    drop -- there would be no way back to healthy even after the underlying
    cause is fixed. Windowing bounds the read to recent volume and lets the
    verdict describe the current period, so it can clear again once a drop
    ages out of the window. It also makes ``drop_rate`` a rolling-window figure
    instead of an all-time one that a burst of drops can no longer move once a
    year of delivered intents has accumulated behind it. One known gap from
    windowing: a document with a missing or malformed ``created_at`` is
    invisible to this filtered scan regardless of how recently it was written
    (see ``_documents``); that class of corruption is not what this check is
    for and remains reachable through the CLI's unwindowed run.
    """

    checked_at = now or datetime.now(timezone.utc)
    normalized = (
        checked_at.replace(tzinfo=timezone.utc) if checked_at.tzinfo is None else checked_at.astimezone(timezone.utc)
    )
    if not is_scheduled_time(normalized):
        return 'not_due'
    window_start = normalized - timedelta(days=HEALTH_CHECK_WINDOW_DAYS)
    try:
        report = collector(None, None, DEFAULT_STALE_AFTER_HOURS, normalized, window_start)
    except Exception as error:
        logger.error(
            '%s review=true status=monitor_error error_class=%s',
            HEALTH_LOG_MARKER,
            type(error).__name__,
        )
        return 'monitor_error'

    alarm = report['dropped'] > 0 or report['undated'] > 0
    status: MaterializationHealthStatus = 'unhealthy' if alarm else 'healthy'
    rate = report['drop_rate']
    log = logger.error if alarm else logger.info
    log(
        '%s review=true alarm=%s status=%s window_days=%d stale_after_hours=%d delivered=%d dropped=%d '
        'in_flight=%d undated=%d decided=%d drop_rate=%s conversation_link_dropped=%d',
        HEALTH_LOG_MARKER,
        str(alarm).lower(),
        status,
        HEALTH_CHECK_WINDOW_DAYS,
        report['stale_after_hours'],
        report['delivered'],
        report['dropped'],
        report['in_flight'],
        report['undated'],
        report['decided'],
        'none' if rate is None else f'{rate:.6f}',
        report['dropped_by_block_type'].get('conversationLink', 0),
    )
    return status


def json_report(report: MaterializationHealthReport) -> str:
    return json.dumps(report, indent=2)
