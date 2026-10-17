"""Held-audio totals for clients. Admission-off callers get nothing and read nothing."""

from datetime import datetime, timezone
from typing import Any

from config.stt_cap_dispatch import execution_admission_enabled
from models.users import HeldAudioRecording, HeldAudioSummary
from utils.stt_cap_dispatch import funded_allowance
from utils.sync.cap_hold import holds

LIST_LIMIT = 200


def next_utc_month_start(now: datetime | None = None) -> int:
    """Monthly reset used by the ladder and the existing at-cap date: 00:00 UTC on the 1st."""
    moment = now or datetime.now(timezone.utc)
    year = moment.year + (1 if moment.month == 12 else 0)
    month = 1 if moment.month == 12 else moment.month + 1
    return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())


def _whole_seconds(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(round(value)))


def _load_rows(uid: str) -> list[dict]:
    loaded = []
    for snap in holds(uid).where('state', '==', 'held').limit(LIST_LIMIT).stream():
        data = snap.to_dict() or {}
        seconds = _whole_seconds(data.get('seconds'))
        if seconds <= 0:
            continue
        started = _whole_seconds(data.get('started_at') or data.get('created_at'))
        if started <= 0:
            continue
        loaded.append({'id': snap.id, 'started_at': started, 'seconds': seconds})
    return loaded


def client_held_audio(
    uid: str,
    *,
    allowance: Any | None = None,
    rows: list[dict] | None = None,
    now: datetime | None = None,
) -> HeldAudioSummary | None:
    """None when admission is off, or when nothing is held and live capture is still funded."""
    if not execution_admission_enabled():
        return None
    if allowance is None:
        allowance = funded_allowance(uid)
    retain_live = not getattr(allowance, 'managed', True)
    if rows is None:
        rows = _load_rows(uid)
    recordings = [
        HeldAudioRecording(id=row['id'], started_at=int(row['started_at']), seconds=int(row['seconds']))
        for row in rows
        if int(row.get('seconds') or 0) > 0 and int(row.get('started_at') or 0) > 0
    ]
    recordings.sort(key=lambda row: row.started_at, reverse=True)
    total = sum(row.seconds for row in recordings)
    if not retain_live and total <= 0:
        return None
    return HeldAudioSummary(
        seconds=total,
        reset_at=next_utc_month_start(now),
        retain_live=retain_live,
        recordings=recordings,
    )
