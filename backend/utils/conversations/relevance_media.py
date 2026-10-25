"""I/O adapter for media/noise classification before notes; no paid shadow work."""

from __future__ import annotations

from typing import Any

from config.refactor_modes import serving_for, shadow_or_serve, shadow_sampled
from utils.capture.media import MAX_SCREEN_ROWS, screen_time
from utils.conversations.relevance_content import FLAG, ContentDecision, classify_content, owner_speech_seconds, value
from utils.conversations.relevance_media_metrics import observe

# Shadow reads evidence, screen rows and boundary state per finalize; a uid sample is enough to measure.
SHADOW_SAMPLE_PERCENT = 5.0


def _speaker_evidence(uid: str, conversation_id: str):
    from utils.speakers.evidence import get_evidence

    return get_evidence(uid, conversation_id)


def _screen_rows(uid: str, start, end):
    from database.screen_activity import get_screen_activity

    return get_screen_activity(uid, start_date=start, end_date=end, limit=MAX_SCREEN_ROWS)


def _boundaries(uid: str):
    from utils.episodes import boundary_store

    windows = boundary_store.windows(uid)
    return boundary_store.load(uid, list(windows))


def _record_boundaries(uid: str, signals):
    from utils.episodes import boundary_store

    return boundary_store.record(uid, signals)


def classify_for_processing(uid: str, conversation: Any, *, user_kept: bool = False) -> ContentDecision | None:
    """Shadow reads evidence and counts only. Serve sets the optional wire field.

    Call after speaker resolution, before any relevance/notes model. No screen or
    speaker text, account identifiers or exception payloads enter diagnostics.
    """
    if not shadow_or_serve(FLAG) or not shadow_sampled(FLAG, uid, SHADOW_SAMPLE_PERCENT):
        return None
    if serving_for(FLAG, uid):
        # A previous classification is not proof about a later transcript revision.
        # In particular, missing evidence on restore must not retain an exclusion.
        conversation.content_kind = None
    if user_kept or value(conversation, 'photos') or value(conversation, 'user_title'):
        if serving_for(FLAG, uid):
            conversation.content_kind = 'conversation'
        observe('classification', 'agree')
        return None
    start, end = screen_time(value(conversation, 'started_at')), screen_time(value(conversation, 'finished_at'))
    if start is None or end is None or end <= start:
        return None
    try:
        evidence = _speaker_evidence(uid, value(conversation, 'id', '') or '')
        segments = value(conversation, 'transcript_segments', ()) or ()
        if owner_speech_seconds(evidence, segments) is None:
            observe('classification', 'agree')
            return None
        boundaries = _boundaries(uid)
        # The existing calendar/screen context can prove an attended call even
        # when its persisted edge is unavailable. Calendar invites cannot.
        external = value(conversation, 'external_data', {}) or {}
        context = value(conversation, 'calendar_meeting_context') or external.get('calendar_meeting_context')
        if context:
            from utils.episodes.boundaries import context_signal

            signal = context_signal(context.model_dump() if hasattr(context, 'model_dump') else context)
            if signal is not None:
                boundaries.append(signal)
        decision = classify_content(
            segments,
            started_at=start,
            finished_at=end,
            evidence=evidence,
            screen_rows=_screen_rows(uid, start, end),
            boundaries=boundaries,
            protected=bool(user_kept or value(conversation, 'photos') or value(conversation, 'user_title')),
        )
    except Exception:
        from utils.observability.fallback import record_fallback

        observe('classification', 'error')
        record_fallback(
            component='other', from_mode='media_noise_evidence', to_mode='legacy', reason='other', outcome='degraded'
        )
        return None
    observe(decision.content_kind, 'agree' if decision.content_kind == 'conversation' else 'disagree')
    if serving_for(FLAG, uid):
        conversation.content_kind = decision.content_kind
        if decision.signals:
            # Use the existing encrypted, account-erased boundary authority.
            # Shadow never writes edges: lifecycle must not observe shadow media.
            try:
                _record_boundaries(uid, list(decision.signals))
            except Exception:
                observe('boundary_write', 'error')
    return decision


def minimum_for_processing(uid: str, conversation: Any, *, user_kept: bool = False):
    """Integrator seam: deterministic title, no notes or generated action items.

    Returns None for every shadow/off user. Preserve history visibility; this
    helper never uses elapsed duration as a relevance-discard reason.
    """
    decision = classify_for_processing(uid, conversation, user_kept=user_kept)
    if decision is None or decision.content_kind == 'conversation' or not serving_for(FLAG, uid):
        return None
    from models.conversation import Structured
    from models.conversation_emoji import fallback_emoji

    # A blank emoji renders as the client's random fallback, not as blank; the
    # media minimum carries the deterministic category emoji like every other
    # no-LLM row.
    return Structured(
        title=decision.title,
        emoji=fallback_emoji('', 'other'),
        title_provenance='server_minimum',
    )
