"""Pure cache validity for the existing server-side, time-based Home policy."""

from datetime import timedelta

from config.episodes import CLOSE_GAP_SECONDS, COMPOSER_MAX_SETTLE_SECONDS
from utils.conversations.fragment_visibility import (
    SETTLING_MAX_HOLD_SECONDS,
    is_completed_below_floor,
    is_settling_fragment,
)
from utils.episodes.policy import utc


def home_clock(rows, members, previous, refreshed, now):
    active = [row for row in rows.values() if not row.get('recorded_merged_into')]
    ids = {cid for row in active for cid in row.get('conversation_ids') or []}
    clocks = {cid: at for cid, at in previous.items() if cid in ids and cid not in refreshed}
    for cid, member in members.items():
        finished = utc(member.get('finished_at'))
        if (
            cid in ids
            and finished is not None
            and not is_completed_below_floor(member)
            and is_settling_fragment(member, now=now.timestamp())
        ):
            clocks[cid] = finished + timedelta(seconds=SETTLING_MAX_HOLD_SECONDS)
        deadline = utc(member.get('episode_transcription_deadline_at'))
        if (
            cid in ids
            and deadline is not None
            and deadline > now
            and not member.get('record_projection_revision')
            and member.get('finalization_status') != 'dead_letter'
            and member.get('status') != 'failed'
            and not member.get('record_upload_failed')
        ):
            clocks[cid] = min(clocks.get(cid, deadline), deadline)
    if len(clocks) > 128:
        raise ValueError('episode_home_clock_capacity')
    candidates = [(at, cid) for cid, at in clocks.items()]
    for row in active:
        last = utc(row.get('last_activity_at'))
        cids = row.get('conversation_ids') or []
        pending = utc(row.get('compose_pending_since'))
        if row.get('status') == 'closed' and pending is not None and cids:
            candidates.append((pending + timedelta(seconds=COMPOSER_MAX_SETTLE_SECONDS), min(cids)))
        if row.get('status') == 'live' and last is not None and cids:
            candidates.append((last + timedelta(seconds=CLOSE_GAP_SECONDS), min(cids)))
    deadline, cid = min(candidates) if candidates else (None, None)
    return {'members': clocks, 'deadline_at': deadline, 'cid': cid}
