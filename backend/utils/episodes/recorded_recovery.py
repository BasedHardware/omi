"""Route a capped capture's evidence once to each recorded-time episode window."""

from dataclasses import replace
from typing import Any, Callable, Mapping, Sequence

from utils.episodes import policy, recovery


def record_windows(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
    collaborators: Any,
    record_moment: Callable,
    *,
    now,
) -> str:
    origin = policy.utc(row.get('started_at'))
    if origin is None:
        return 'no_episode'
    if not windows:
        return 'no_episode'
    # Membership is singular. Retain the whole conversation's evidence in its
    # owner, including speech beyond the owner's visible four-hour window.
    owner = windows[0]
    outcome = 'skipped_applied'
    for moment in recovery.moments(conversation_id, row, now=now, calendar_identity=row.get('calendar_identity')):
        moment = replace(moment, ended_at=min(moment.ended_at, owner['last_activity_at']))
        outcome = record_moment(uid, moment, collaborators, member_episode_id=str(owner['id']))
        if outcome not in {'applied', 'skipped_applied'}:
            return outcome
    return outcome
