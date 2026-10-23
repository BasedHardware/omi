"""Atomic monthly usage counters; hourly documents remain the reconciliation source.

Maintenance is unconditional, including while the reader lever is disabled.
Enable readers only after every hourly writer has this contract (see docs).
"""

import calendar
from contextlib import contextmanager
from datetime import datetime, timezone
import math
import os
import re
from typing import Any, Callable, Iterator

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.firestore_read_levers import lever_enabled
from database._client import get_firestore_client
from database.firestore_read_origin import read_origin
from database.legal_holds import DestructiveOperationInProgress, external_write_fence
from utils.observability.fallback import record_fallback

FIELDS = ('transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds')
SCHEMA_VERSION = 1


class UsagePublicationRootMissing(DestructiveOperationInProgress):
    """Usage must not recreate children after the account root disappears."""


@contextmanager
def publication_fence(user_ref: Any, transaction: Any, *, firestore_client: Any) -> Iterator[None]:
    """Hold erasure authorities and the user root through aggregate publication."""
    with external_write_fence(user_ref.id, firestore_client=firestore_client, transaction=transaction):
        if not user_ref.get(transaction=transaction).exists:
            raise UsagePublicationRootMissing('usage publication requires an existing user')
        yield


def commit_fenced(user_ref: Any, write: Callable[[Any], None], *, firestore_client: Any) -> None:
    """Retry one bounded source/aggregate commit after fresh authority reads.

    The callback must only queue Firestore writes, so retries cannot duplicate
    external side effects. Previously unfenced writers pay three point reads.
    """

    @firestore.transactional
    def commit(transaction: Any) -> None:
        with publication_fence(user_ref, transaction, firestore_client=firestore_client):
            write(transaction)

    commit(firestore_client.transaction())


def month_ref(user_ref: Any, date: datetime) -> Any:
    return user_ref.collection('monthly_usage_totals').document(f'{date.year}-{date.month:02d}')


def queue_increment(writer: Any, user_ref: Any, date: datetime, update_doc: dict) -> None:
    """Reuse source transforms and once receipts under the caller's publication fence."""
    increments = {key: update_doc[key] for key in FIELDS if key in update_doc}
    if increments:
        writer.set(
            month_ref(user_ref, date),
            {'totals': increments, 'days': {f'{date.day:02d}': increments}},
            merge=True,
        )


def queue_invalidation(writer: Any, user_ref: Any, date: datetime) -> None:
    """Overwrite/reset/delete sources and invalidate their total in ONE commit."""
    writer.set(month_ref(user_ref, date), {'ready': False}, merge=True)


def _epoch() -> str:
    value = os.environ.get('FSR_USAGE_MONTH_TOTAL_EPOCH', 'v1')
    # Empty/malformed epochs must never accidentally reuse a ready total.
    return value if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) else ''


def _numeric_stats(value: Any) -> bool:
    return isinstance(value, dict) and all(
        type(value.get(key, 0)) in (int, float) and math.isfinite(value.get(key, 0)) for key in FIELDS
    )


def _ready(data: dict, epoch: str, date: datetime) -> bool:
    days = data.get('days')
    return (
        data.get('ready') is True
        and data.get('schema_version') == SCHEMA_VERSION
        and data.get('epoch') == epoch
        and _numeric_stats(data.get('totals'))
        and isinstance(days, dict)
        and all(
            day in {f'{i:02d}' for i in range(1, calendar.monthrange(date.year, date.month)[1] + 1)}
            and _numeric_stats(stats)
            for day, stats in days.items()
        )
    )


def _month_rows(user_ref: Any, date: datetime, transaction: Any) -> Any:
    return (
        user_ref.collection('hourly_usage')
        .where(filter=FieldFilter('year', '==', date.year))
        .where(filter=FieldFilter('month', '==', date.month))
        .stream(transaction=transaction)
    )


@firestore.transactional
@read_origin('job:usage_month_total_rebuild')
def _rebuild(transaction: Any, user_ref: Any, date: datetime, epoch: str, *, firestore_client: Any) -> dict | None:
    """Source scan and publication share a snapshot and conflict with ALL writers."""
    # A read now materializes derived user data. Use the existing transaction
    # fence so deletion cannot inventory the subtree before this write lands.
    # Read authorities before the counter, matching fenced source writers.
    with external_write_fence(user_ref.id, firestore_client=firestore_client, transaction=transaction):
        if not user_ref.get(transaction=transaction).exists:
            return None
        ref = month_ref(user_ref, date)
        current = ref.get(transaction=transaction).to_dict() or {}
        if _ready(current, epoch, date):
            return current
        totals = dict.fromkeys(FIELDS, 0)
        days: dict[str, dict] = {}
        for snap in _month_rows(user_ref, date, transaction):
            row = snap.to_dict() or {}
            # The original since query filters on the stored id, not the document
            # name or day field. Refuse anomalies rather than silently omit them.
            try:
                stamp = datetime.strptime(snap.id, '%Y-%m-%d-%H')
            except (TypeError, ValueError):
                return None
            if (
                snap.id != stamp.strftime('%Y-%m-%d-%H')
                or row.get('id') != snap.id
                or stamp.year != date.year
                or stamp.month != date.month
                or not _numeric_stats(row)
            ):
                return None
            day = days.setdefault(f'{stamp.day:02d}', dict.fromkeys(FIELDS, 0))
            for key in FIELDS:
                totals[key] += row.get(key, 0)
                day[key] += row.get(key, 0)
        data = {
            'schema_version': SCHEMA_VERSION,
            'epoch': epoch,
            'ready': True,
            'totals': totals,
            'days': days,
            'rebuilt_at': datetime.now(timezone.utc),
        }
        # Replace: a reset may have invalidated stale daily fields, and concurrent
        # increments must conflict/retry rather than merge into an old baseline.
        transaction.set(ref, data)
        return data


@read_origin('job:usage_month_total_read')
def read_monthly_totals(
    uid: str, date: datetime, *, firestore_client: Any = None, start_date: datetime | None = None
) -> dict | None:
    """One warm document read, including arbitrary day-cutoff and late updates.

    None requests the unchanged hourly query. Redis and reader cohort selection
    do not participate in accounting or maintenance.
    """
    if not lever_enabled('usage_month_total', uid) or not (epoch := _epoch()):
        return None
    try:
        firestore_client = firestore_client if firestore_client is not None else get_firestore_client()
        user_ref = firestore_client.collection('users').document(uid)
        data = month_ref(user_ref, date).get().to_dict() or {}
        if not _ready(data, epoch, date):
            data = _rebuild(firestore_client.transaction(), user_ref, date, epoch, firestore_client=firestore_client)
        if data is not None:
            if start_date is None or (start_date.year, start_date.month) < (date.year, date.month):
                return {key: data['totals'].get(key, 0) for key in FIELDS}
            stats = dict.fromkeys(FIELDS, 0)
            if (start_date.year, start_date.month) == (date.year, date.month):
                for day, values in data['days'].items():
                    if int(day) >= start_date.day:
                        for key in FIELDS:
                            stats[key] += values.get(key, 0)
            return stats
    except Exception:
        # Do not retain a stale total on transaction/read failure.
        pass
    record_fallback(
        component='firestore_read',
        from_mode='monthly_total',
        to_mode='hourly_query',
        reason='unavailable',
        outcome='recovered',
    )
    return None
