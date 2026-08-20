"""Read-only health reporting for Chat-first proactive materialization."""

from __future__ import annotations

import collections
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Iterator, List, Literal, TypedDict, cast

from database._client import get_firestore_client
from database.chat_first_intents import INTENTS_COLLECTION

DEFAULT_STALE_AFTER_HOURS = 48
SCHEDULED_WEEKDAY_UTC = 0  # Monday
SCHEDULED_HOUR_UTC = 14
HEALTH_LOG_MARKER = 'chat_first_materialization_health'
DELIVERED = 'delivered'

logger = logging.getLogger(__name__)


class MaterializationHealthReport(TypedDict):
    scope: str
    stale_after_hours: int
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
MaterializationHealthCollector = Callable[[str | None, int | None, int, datetime], MaterializationHealthReport]


def _documents(
    uid: str | None,
    limit: int | None,
    *,
    firestore_client: Any = None,
) -> Iterator[Dict[str, Any]]:
    """Stream intent documents without requiring a composite Firestore index."""

    client = firestore_client or get_firestore_client()
    if uid:
        query: Any = client.collection('users').document(uid).collection(INTENTS_COLLECTION)
    else:
        query = client.collection_group(INTENTS_COLLECTION)
    if limit is not None:
        query = query.limit(limit)
    for snapshot in query.stream():
        raw: object = snapshot.to_dict()
        if isinstance(raw, dict):
            yield cast(Dict[str, Any], raw)


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
) -> MaterializationHealthReport:
    """Bucket intent documents into delivered, dropped, in-flight, and malformed."""

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
    *,
    firestore_client: Any = None,
) -> MaterializationHealthReport:
    return summarize(
        _documents(uid, limit, firestore_client=firestore_client),
        scope=uid or 'all_accounts',
        stale_after_hours=stale_after_hours,
        now=now,
    )


def render(report: MaterializationHealthReport) -> str:
    rate = report['drop_rate']
    lines = [
        f"scope                {report['scope']}",
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
    """

    checked_at = now or datetime.now(timezone.utc)
    normalized = (
        checked_at.replace(tzinfo=timezone.utc) if checked_at.tzinfo is None else checked_at.astimezone(timezone.utc)
    )
    if not is_scheduled_time(normalized):
        return 'not_due'
    try:
        report = collector(None, None, DEFAULT_STALE_AFTER_HOURS, normalized)
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
        '%s review=true alarm=%s status=%s stale_after_hours=%d delivered=%d dropped=%d '
        'in_flight=%d undated=%d decided=%d drop_rate=%s conversation_link_dropped=%d',
        HEALTH_LOG_MARKER,
        str(alarm).lower(),
        status,
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
