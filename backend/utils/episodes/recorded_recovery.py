"""Route a capped capture's evidence once to each recorded-time episode window."""

from dataclasses import replace
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from database import episode_receipts
from utils.episodes import policy, recovery
from utils.episodes.moment import MomentInput


def unconsumed_moments(
    uid: str, conversation_id: str, moments: Iterable[MomentInput], collaborators: Any
) -> Iterator[MomentInput]:
    """Read the receipts once for the whole walk: a long capture replays hundreds of finished batches,
    and each would otherwise re-read the episode and every receipt shard just to skip itself."""
    try:
        client = collaborators.firestore_client
        legacy, _ = episode_receipts.get_consumed_ids(uid, conversation_id, all_shards=True, firestore_client=client)
        content, _ = episode_receipts.get_consumed_ids(
            uid, recovery.receipt_namespace(conversation_id), all_shards=True, firestore_client=client
        )
    except Exception:
        yield from moments
        return
    for moment in moments:
        if recovery.select_segments(moment.segments, legacy, content, -1.0, recovered=True)[0]:
            yield moment


def record_walk(
    uid: str, episode_id: str, walk: Iterable[MomentInput], collaborators: Any, record_moment: Callable
) -> str:
    outcome = 'skipped_applied'
    for moment in walk:
        outcome = record_moment(uid, moment, collaborators, member_episode_id=episode_id)
        if outcome not in {'applied', 'skipped_applied'}:
            return outcome
    return outcome


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
    walk = recovery.moments(conversation_id, row, now=now, calendar_identity=row.get('calendar_identity'))
    for moment in unconsumed_moments(uid, conversation_id, walk, collaborators):
        moment = replace(moment, ended_at=min(moment.ended_at, owner['last_activity_at']))
        outcome = record_moment(uid, moment, collaborators, member_episode_id=str(owner['id']))
        if outcome not in {'applied', 'skipped_applied'}:
            return outcome
    return outcome
