"""Held-audio totals for clients. The dispatch flag off reads nothing and adds no field."""

from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from config.stt_cap_dispatch import any_execution_admission_enabled as enabled, execution_admission_enabled
from models.users import HeldAudioRecording, HeldAudioSummary
from utils.stt_cap_dispatch import funded_allowance
from utils.sync.cap_hold import holds, whole_seconds, ensure_summary, remaining_seconds

# Newest-first page. The exact total lives on the summary doc, not this page.
LIST_LIMIT = 20


def next_utc_month_start(now: datetime | None = None) -> int:
    """00:00 UTC on the 1st. The transcription minute counter and the ladder budget both roll here."""
    moment = now or datetime.now(timezone.utc)
    year = moment.year + (1 if moment.month == 12 else 0)
    month = 1 if moment.month == 12 else moment.month + 1
    return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())


def plan_reset_at(subscription: Any = None, now: datetime | None = None) -> int:
    """When this account's transcription limit next reopens, computed on the server.

    Hourly usage is aggregated by UTC year and month, and the ladder budget uses
    the same boundary. A legacy Plus Stripe ``current_period_end`` can fall on
    any day, but that renewal does not reopen the minute counter, so promising
    it would transcribe before the date. The client displays this instant and
    does not compute a month boundary itself.
    """
    del subscription
    return next_utc_month_start(now)


def _load_summary(uid: str) -> dict:
    return ensure_summary(uid)


def _load_rows(uid: str) -> list[dict]:
    loaded = []
    query = (
        holds(uid)
        .where('state', 'in', ['held', 'retained'])
        .order_by('listed_at', direction=firestore.Query.DESCENDING)
        .limit(LIST_LIMIT)
    )
    for snap in query.stream():
        data = snap.to_dict() or {}
        seconds = whole_seconds(remaining_seconds(data))
        if seconds <= 0:
            continue
        started = whole_seconds(data.get('started_at') or data.get('created_at'))
        if started <= 0:
            continue
        loaded.append({'id': snap.id, 'started_at': started, 'seconds': seconds})
    return loaded


def _recordings(rows: list[dict]) -> list[HeldAudioRecording]:
    recordings = [
        HeldAudioRecording(id=row['id'], started_at=int(row['started_at']), seconds=int(row['seconds']))
        for row in rows
        if int(row.get('seconds') or 0) > 0 and int(row.get('started_at') or 0) > 0
    ]
    recordings.sort(key=lambda row: row.started_at, reverse=True)
    return recordings


def client_held_audio(
    uid: str,
    *,
    allowance: Any | None = None,
    rows: list[dict] | None = None,
    summary: dict | None = None,
    subscription: Any = None,
    now: datetime | None = None,
) -> HeldAudioSummary | None:
    """None when dispatch enforcement is off, or when nothing is held and live capture is still funded.

    The allowance is the one the subscription endpoint already resolved. This
    function does not call ``funded_allowance`` when that object is passed.
    With the flag on and a positive summary count, the reads are the summary
    document plus one ordered query of at most ``LIST_LIMIT`` holds.
    """
    if not enabled(uid):
        return None
    if allowance is None:
        allowance = funded_allowance(uid)
    retain_live = execution_admission_enabled(uid, 'live') and not getattr(allowance, 'managed', True)
    injected_rows = rows is not None
    total = 0
    count = 0
    if summary is None and not injected_rows:
        summary = _load_summary(uid)
    if summary is not None:
        total = whole_seconds(summary.get('seconds'))
        count = summary.get('count') or 0
        count = int(count) if isinstance(count, int) and not isinstance(count, bool) and count > 0 else 0
        if rows is None and count > 0:
            rows = _load_rows(uid)
    recordings = _recordings(rows or [])
    if summary is None:
        total = sum(row.seconds for row in recordings)
        count = len(recordings)
    if not retain_live and total <= 0:
        return None
    return HeldAudioSummary(
        seconds=total,
        reset_at=plan_reset_at(subscription, now),
        retain_live=retain_live,
        state='paused' if retain_live else 'recovering',
        count=count,
        recordings=recordings[:LIST_LIMIT],
    )


def attach_subscription_held_audio(response: Any, uid: str, allowance: Any, subscription: Any = None) -> None:
    """Attach the summary without starting recovery. No-op, and no field, when dispatch enforcement is off."""
    if not enabled(uid):
        return
    response.held_audio = client_held_audio(uid, allowance=allowance, subscription=subscription)
