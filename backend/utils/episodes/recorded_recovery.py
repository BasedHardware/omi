"""Route a capped capture's evidence once to each recorded-time episode window."""

from dataclasses import replace
from datetime import timedelta
from typing import Any, Callable, Mapping, Sequence

from config.episodes import MAX_EPISODE_SECONDS
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
    outcome = 'skipped_applied'
    for index, window in enumerate(windows):
        lo = window['started_at']
        hi = (
            windows[index + 1]['started_at']
            if index + 1 < len(windows)
            else lo + timedelta(seconds=MAX_EPISODE_SECONDS)
        )
        selected = [
            s
            for s in row.get('transcript_segments') or []
            if isinstance(s, Mapping)
            and (
                (index == 0 and (s.get('audio_alignment') == 'unplaced' or recovery.segment_start(s) < 0))
                or (
                    s.get('audio_alignment') != 'unplaced'
                    and recovery.segment_start(s) >= 0
                    and lo <= origin + timedelta(seconds=recovery.segment_start(s)) < hi
                )
            )
        ]
        if not selected:
            continue
        snapshot = {**row, 'transcript_segments': selected, 'finished_at': min(window['last_activity_at'], hi)}
        for moment in recovery.moments(
            conversation_id, snapshot, now=now, calendar_identity=row.get('calendar_identity')
        ):
            moment = replace(moment, started_at=max(origin, lo), ended_at=min(moment.ended_at, hi))
            outcome = record_moment(uid, moment, collaborators, member_episode_id=str(window['id']))
            if outcome not in {'applied', 'skipped_applied'}:
                return outcome
    return outcome
