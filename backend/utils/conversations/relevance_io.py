"""The I/O side of the relevance step: lookups, the model-withheld path, and recording.

``relevance.py`` stays pure (policy and tiers); this module holds what touches
Firestore or metrics, so ``process_conversation`` only wires them together.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable, Optional

from config.recorded_time_tolerances import CLOCK_SKEW_SECONDS
from database import conversations as conversations_db
from models.conversation_continuity import DEFAULT_GAP_SECONDS
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import (
    RELEVANCE_DECISION_FIELD,
    Neighbor,
    RelevanceDecision,
    decide_relevance,
    find_neighbor,
)
from utils.conversations.fragment_visibility import is_relevance_discarded
from utils.conversations.wake_word import find_wake_word_matches
from utils.integration_telemetry import emit_posthog_event
from utils.metrics import record_conversation_relevance
from utils.release_probe import is_release_probe_uid

logger = logging.getLogger(__name__)

NEIGHBOR_CANDIDATE_LIMIT = 10


def adjacent_conversation(
    uid: str, conversation: Any, conversation_id: Optional[str], *, require_complete: bool = False
) -> Optional[Neighbor]:
    """A kept conversation this one would have joined had capture not split it (fail-open)."""
    from utils.conversations.recorded_time import conversation_span

    span = conversation_span(conversation)
    started_at, finished_at = (span.recorded_start, span.recorded_end) if span else (None, None)
    if started_at is None or finished_at is None:
        return None
    try:
        rows = conversations_db.get_conversations_finished_after(
            uid,
            status='completed',
            # Legacy finished_at can lag the recording clock. Widen discovery;
            # find_neighbor still proves adjacency from recorded spans below.
            finished_after=started_at - timedelta(seconds=DEFAULT_GAP_SECONDS + CLOCK_SKEW_SECONDS),
            limit=NEIGHBOR_CANDIDATE_LIMIT,
            **({'include_hidden': True} if require_complete else {}),
        )
    except Exception as error:
        if require_complete:
            raise
        logger.warning('relevance neighbor lookup failed uid=%s: %s', uid, error)
        return None
    found = find_neighbor(
        rows,
        conversation_id=conversation_id or getattr(conversation, 'id', None),
        started_at=started_at,
        finished_at=finished_at,
        gap_seconds=DEFAULT_GAP_SECONDS,
    )
    if require_complete and found is None and len(rows) >= NEIGHBOR_CANDIDATE_LIMIT:
        raise RuntimeError('neighbor_window_incomplete')
    return found


def occasion_retention(uid: str, conversation: Any, conversation_id: Optional[str] = None) -> Optional[str]:
    """Prove isolation before admitting a standalone discard; metadata only.

    Another kept member must support recorded-time ownership, before or after
    this clip attaches. A singleton created by this clip cannot prove its own
    relevance. Lookup failure keeps content, never proves isolation.
    """
    from config.occasion_relevance import enabled

    if not enabled():
        return None
    from database import episodes, episode_timeline
    from utils.episodes.timeline import episode_owning_recorded_time, choose_recorded_episode

    cid = conversation_id or getattr(conversation, 'id', None)
    from utils.conversations.recorded_time import conversation_span

    span = conversation_span(conversation)
    start, end = (span.recorded_start, span.recorded_end) if span else (None, None)
    if start is None or end is None:
        return None
    try:
        member = episodes.get_episode_for_conversation(uid, cid) if cid else None
        owner = episode_owning_recorded_time(uid, start, ended_at=end)
        for episode in [member, owner]:
            if not episode:
                continue
            for other_id in episode.get('conversation_ids') or []:
                if other_id == cid:
                    continue
                other = conversations_db.get_conversation_raw_snapshot(
                    uid,
                    other_id,
                    field_paths=[
                        'started_at',
                        'finished_at',
                        'discarded',
                        'deleted',
                        'sync_merged_into',
                        'recorded_start',
                        'recorded_end',
                        'last_speech_at',
                        'status',
                        'capture_evidence',
                        'relevance_decision',
                        'sync_relevance_user_kept',
                        'has_photos',
                        'photos',
                        'user_title',
                        'starred',
                        'folder_user_set',
                    ],
                )
                if (
                    not other
                    or is_relevance_discarded(other)
                    or any(other.get(key) for key in ('deleted', 'sync_merged_into'))
                ):
                    continue
                # Check the other member's span, not an envelope this clip may
                # already have extended. Attachment order cannot widen proof.
                other_span = conversation_span(other)
                if other_span is None:
                    continue
                evidence = dict(episode, started_at=other_span.recorded_start, last_activity_at=other_span.recorded_end)
                if choose_recorded_episode([evidence], start, end):
                    from config.recorded_time import recorded_episodes_enabled
                    from utils.episodes.client_gate import episode_work_enabled

                    # Context remains useful outside episode admission, but a
                    # keep receipt must not claim membership we cannot write.
                    if not recorded_episodes_enabled() or not episode_work_enabled(uid):
                        return 'occasion_context'
                    if not cid:
                        return 'occasion_lookup_unavailable'
                    source = (
                        conversation.get('source')
                        if isinstance(conversation, dict)
                        else getattr(conversation, 'source', None)
                    )
                    episode_timeline.attach_existing_recorded(
                        uid,
                        cid,
                        getattr(source, 'value', source),
                        start,
                        end,
                        episode_id=episode['id'],
                        choose=choose_recorded_episode,
                    )
                    return 'occasion_member'
        if adjacent_conversation(uid, conversation, cid, require_complete=True):
            return 'occasion_neighbor'
    except Exception as error:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='conversation_relevance',
            from_mode='occasion_lookup',
            to_mode='retain',
            reason='lookup_unavailable',
            outcome='degraded',
        )
        logger.warning('event=occasion_retention outcome=lookup_unavailable exception_type=%s', type(error).__name__)
        return 'occasion_lookup_unavailable'
    return None


def rules_only_relevance(
    uid: str,
    conversation: Any,
    trigger: ProcessingTrigger,
    user_kept: bool,
    calendar_retains: Callable[[], bool],
) -> RelevanceDecision:
    """The relevance step where the plan withholds the model (free-tier desktop).

    The rules cost nothing, so capture that stores without enrichment is still
    assessed; anything they cannot settle is kept. Any wake-word match skips the
    rules entirely, the conservative reading of the model path's trusted marker.
    """
    segments = list(getattr(conversation, 'transcript_segments', None) or [])
    return decide_relevance(
        trigger=trigger,
        texts=[segment.text for segment in segments],
        speech_seconds=None,
        has_photos=any((photo.description or '').strip() for photo in getattr(conversation, 'photos', None) or []),
        user_kept=user_kept,
        exempt=is_release_probe_uid(uid),
        trusted_wake_word=bool(find_wake_word_matches(segments)),
        model_discards=None,
        calendar_retains=calendar_retains,
        occasion_retains=lambda: occasion_retention(uid, conversation),
    )


def record_decision(decision: RelevanceDecision) -> None:
    record_conversation_relevance(
        trigger=decision.trigger.value,
        verdict=decision.verdict,
        decided_by=decision.decided_by,
        reason=decision.reason,
    )


def apply_relevance(conversation: Any, payload: dict[str, Any], decision: RelevanceDecision) -> None:
    """Stamp a decision onto an in-memory conversation and its persist payload."""
    conversation.discarded = decision.discard
    payload['discarded'] = decision.discard
    payload[RELEVANCE_DECISION_FIELD] = decision.as_record()
    record_decision(decision)


def emit_recorded_decision(uid: str, conversation_id: str, decision: RelevanceDecision) -> None:
    """Enqueue one content-free event after a final decision is successfully stored.

    The shared PostHog helper uses the SDK's background capture queue. Optional
    analytics must never fail conversation processing, even if capture raises.
    """
    try:
        properties: dict[str, Any] = {
            'conversation_id': str(conversation_id),
            'reason': decision.reason,
            'discarded': decision.discard,
        }
        if decision.arm is not None:
            properties['arm'] = decision.arm
        if decision.jev_threshold is not None and decision.jev_comparison is not None:
            properties['jev_threshold'] = decision.jev_threshold
            properties['jev_comparison'] = decision.jev_comparison
        emit_posthog_event(uid, 'Relevance Decision Recorded', properties)
    except Exception as error:
        logger.warning('relevance analytics capture failed error=%s', type(error).__name__)
