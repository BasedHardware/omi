"""Episode integration of the hard-boundary authority; no extra model calls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from config.occasion_conversations import EPISODE_BOUNDARIES_MODE_ENV
from config.refactor_modes import serving_for, shadow_or_serve
from database import episodes as episodes_db
from utils.episodes import boundaries, boundary_store, policy
from utils.conversations.lifecycle_metrics import observe


def _decision(
    uid: str,
    episode: Mapping | None,
    facts: policy.MomentFacts,
    legacy: policy.Boundary,
    *,
    firestore_client: Any = None,
) -> policy.Boundary:
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return legacy
    known = boundary_store.windows(uid, firestore_client=firestore_client)
    current = boundaries.active(known, facts.started_at)
    previous = boundaries.active(known, policy.utc((episode or {}).get('started_at')) or facts.started_at)
    proposed = legacy
    if episode and current != previous:
        proposed = policy.Boundary('close', 'boundary')
    elif current:
        # A meeting stays whole even across source changes and occasion caps.
        proposed = policy.Boundary(policy.CONTINUE if episode else policy.NEW)
    observe('episode_boundary', proposed == legacy)
    return proposed if serving_for(EPISODE_BOUNDARIES_MODE_ENV, uid) else legacy


def decision(uid, episode, facts, legacy, *, firestore_client=None):
    try:
        return _decision(uid, episode, facts, legacy, firestore_client=firestore_client)
    except Exception:
        observe('episode_boundary', None)
        return legacy


def apply_signal_edges(
    uid: str, *, now: datetime | None = None, quiet: bool = False, firestore_client: Any = None
) -> str:
    """Intake fast path: close on a new signal edge, open the meeting episode.

    The live controller owns conversation finalization; this only changes its
    overlay. A restarted process can replay the edge from durable timestamps.
    """
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return 'disabled'
    now = now or datetime.now(timezone.utc)
    known = boundary_store.windows(uid, firestore_client=firestore_client)
    episode = episodes_db.get_current_episode(uid, firestore_client=firestore_client)
    current = boundaries.active(known, now)
    started = policy.utc((episode or {}).get('started_at'))
    changed = bool(episode and started and boundaries.crossed(known, started, now))
    observe('episode_signal', not changed)
    if not serving_for(EPISODE_BOUNDARIES_MODE_ENV, uid):
        return 'shadow'
    if episode is not None and (changed or quiet):
        episodes_db.close_episode(uid, str(episode['id']), 'boundary', closed_at=now, firestore_client=firestore_client)
        episode = None
    if episode is None and current and not quiet:
        from utils.episodes.service import new_episode

        start = max(start for key in current if (start := policy.utc(known[key]['started_at'])) is not None)
        base = new_episode(conversation_id='', started_at=start, last_activity_at=now, calendar_identity=None, now=now)
        episodes_db.commit_moment(
            uid,
            expected_episode_id=None,
            expected_version=None,
            new_episode=base,
            link_conversation_ids=[],
            firestore_client=firestore_client,
        )
        return 'opened'
    return 'closed' if changed or quiet else 'unchanged'
