"""Default-off, metadata-only desktop call linking contract (no provider IO)."""

from __future__ import annotations

import hashlib
import math
import os
from datetime import datetime, timezone
from typing import Any, Mapping

MODE_ENV = 'DESKTOP_PENDANT_CALL_LINK_MODE'
PERCENT_ENV = 'DESKTOP_PENDANT_CALL_LINK_PERCENT'
CALL_GROUP_KIND = 'desktop_pendant_call'


def call_link_mode(uid: str) -> str:
    mode = os.getenv(MODE_ENV, 'off').strip().lower()
    if mode not in {'shadow', 'on'}:
        return 'off'
    if mode == 'shadow':
        return mode  # Observe the entire fleet, irrespective of the on cohort.
    try:
        percent = float(os.getenv(PERCENT_ENV, '100'))
    except ValueError:
        return 'off'
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        return 'off'
    bucket = int.from_bytes(hashlib.sha256(f'{CALL_GROUP_KIND}:{uid}'.encode()).digest()[:8], 'big') / 2**64
    return 'on' if bucket * 100 < percent else 'off'


def desktop_meeting(row: Mapping[str, Any]) -> bool:
    return row.get('source') == 'desktop' and (row.get('external_data') or {}).get('conversation_role') == 'meeting'


def window(row: Mapping[str, Any]) -> tuple[datetime, datetime] | None:
    start, finish = row.get('started_at'), row.get('finished_at')
    if not isinstance(start, datetime) or not isinstance(finish, datetime):
        return None
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    finish = finish if finish.tzinfo else finish.replace(tzinfo=timezone.utc)
    return (start, finish) if finish > start else None


def capture_windows(*rows: Mapping[str, Any]) -> dict[str, tuple[datetime, datetime]] | None:
    """Only validated windows may be handed to the transaction fence."""
    result = {}
    for row in rows:
        observed = window(row)
        cid = row.get('id')
        if observed is None or not isinstance(cid, str) or not cid:
            return None
        result[cid] = observed
    return result


def call_pair(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict | None:
    if a.get('id') == b.get('id') or not a.get('id') or not b.get('id'):
        return None
    if not ((desktop_meeting(a) and b.get('source') == 'omi') or (desktop_meeting(b) and a.get('source') == 'omi')):
        return None
    if any(
        r.get('status') != 'completed' or any(r.get(k) for k in ('deleted', 'discarded', 'capture_group_closed'))
        for r in (a, b)
    ):
        return None
    aw, bw = window(a), window(b)
    if aw is None or bw is None:
        return None
    overlap = (min(aw[1], bw[1]) - max(aw[0], bw[0])).total_seconds()
    ratio = overlap / min((aw[1] - aw[0]).total_seconds(), (bw[1] - bw[0]).total_seconds())
    if overlap < 30 or ratio < 0.5:
        return None
    return {'method': CALL_GROUP_KIND, 'overlap_seconds': overlap, 'overlap_ratio': ratio}


def without_capture_metadata(row: Mapping[str, Any]) -> dict:
    """Only for a verified call-group continuation; retain every actual edit guard."""
    external = dict(row.get('external_data') or {})
    external.pop('duplicate_capture_of', None)
    return {**row, 'capture_group': None, 'external_data': external}
