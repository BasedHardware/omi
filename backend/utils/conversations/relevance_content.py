"""Content-kind policy and the shared derived-consumer gate. Duration never discards."""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from config.refactor_modes import serving_for, shadow_or_serve
from models.boundary_evidence import BoundarySignal
from models.conversation_enums import ContentKind
from models.speaker_evidence import OWNER, SpeakerEvidence
from utils.capture.media import media_playback_signals, screen_time
from utils.conversations.relevance_rules import EXPLICIT_REMINDER_RE, transcript_word_count
from utils.conversations.relevance_media_metrics import observe
from utils.conversations.owner_attribution import speaker_role_map

MEDIA_NOISE_MODE_ENV = 'MEDIA_NOISE_MODE'
FLAG = MEDIA_NOISE_MODE_ENV
# Declare derived cohort names for registry tooling, read only through refactor_modes.
MEDIA_SERVE_PERCENT_ENV = 'MEDIA_NOISE_MODE_SERVE_PERCENT'
MEDIA_SERVE_DIGESTS_ENV = 'MEDIA_NOISE_MODE_SERVE_UID_SHA256S'
OWNER_FLOOR_SECONDS = 2.0
WORD_FLOOR = 12
BYSTANDER_MIN_SECONDS = 10 * 60
logger = logging.getLogger(__name__)


def value(row: Any, name: str, default: Any = None) -> Any:
    return row.get(name, default) if isinstance(row, Mapping) else getattr(row, name, default)


@dataclass(frozen=True)
class ContentDecision:
    content_kind: ContentKind
    reason: str
    owner_seconds: float | None
    words: int
    signals: tuple[BoundarySignal, ...] = ()

    @property
    def title(self) -> str:
        if self.content_kind == 'media':
            return (
                f'Watched: {self.signals[0].title or "Media playback"}' if self.signals else 'Watched: Media playback'
            )
        return 'Ambient audio'


def owner_speech_seconds(evidence: SpeakerEvidence | None, segments: Sequence[Any]) -> float | None:
    """Consume producer bands, without re-thresholding probability or legacy is_user.

    Missing/partial/stale evidence is unknown, never evidence of owner absence.
    A plausible acoustic owner protects its whole cluster against exclusion,
    without granting owner attribution. Manual decisions protect only their
    explicitly bound segments.
    """
    if evidence is None or evidence.status != 'resolved' or not evidence.clusters:
        return None
    ids = {str(value(s, 'id')) for s in segments if value(s, 'id')}
    covered = {sid for cluster in evidence.clusters for sid in cluster.segment_ids}
    if not ids or len(ids) != len(segments) or ids != covered:
        return None
    seconds = 0.0
    for cluster in evidence.clusters:
        if not math.isfinite(cluster.speech_seconds) or cluster.speech_seconds < 0:
            return None
        owners = [
            c
            for c in cluster.candidates
            if c.person_id == OWNER and c.band in ('confident', 'likely') and c.source != 'roster'
        ]
        if any(c.source != 'manual' for c in owners):
            seconds += cluster.speech_seconds
        elif owners:
            # A one-second manual excerpt cannot turn twenty minutes of a
            # bystander's voice into owner speech. Older unscoped evidence is
            # unknown and therefore conservatively abstains from exclusion.
            if any(c.segment_ids is None for c in owners):
                return None
            manual_ids = {sid for c in owners for sid in c.segment_ids or ()}
            if not manual_ids or not manual_ids.issubset(cluster.segment_ids):
                return None
            for segment in segments:
                if str(value(segment, 'id')) not in manual_ids:
                    continue
                start, end = value(segment, 'start'), value(segment, 'end')
                if (
                    not isinstance(start, (int, float))
                    or not isinstance(end, (int, float))
                    or not math.isfinite(start)
                    or not math.isfinite(end)
                    or end < start
                ):
                    return None
                seconds += end - start
    return seconds


def _owner_in_call(signals: Sequence[BoundarySignal], start: datetime, end: datetime) -> bool:
    # Calendar presence alone is not evidence of a joined call. Media never counts.
    return any(
        s.kind in ('phone_call', 'desktop_meeting', 'screen_meeting')
        and (left := screen_time(s.started_at)) is not None
        and left < end
        and (s.ended_at is None or (screen_time(s.ended_at) or start) > start)
        for s in signals
    )


def classify_content(
    segments: Sequence[Any],
    *,
    started_at: datetime,
    finished_at: datetime,
    evidence: SpeakerEvidence | None,
    screen_rows: Sequence[Mapping[str, Any]] = (),
    boundaries: Sequence[BoundarySignal] = (),
    protected: bool = False,
) -> ContentDecision:
    texts = [str(value(s, 'text', '') or '') for s in segments]
    words = sum(transcript_word_count(t) for t in texts)
    owner_seconds = owner_speech_seconds(evidence, segments)
    start, end = screen_time(started_at), screen_time(finished_at)
    if protected or any(EXPLICIT_REMINDER_RE.search(t) for t in texts):
        return ContentDecision('conversation', 'protected', owner_seconds, words)
    if start is None or end is None or end <= start:
        return ContentDecision('conversation', 'unknown_window', owner_seconds, words)
    if _owner_in_call(boundaries, start, end):
        return ContentDecision('conversation', 'owner_in_call', owner_seconds, words)
    if owner_seconds is None:
        return ContentDecision('conversation', 'unknown_owner', None, words)
    if owner_seconds <= OWNER_FLOOR_SECONDS:
        signals = media_playback_signals(screen_rows, started_at=start, finished_at=end)
        if signals:
            return ContentDecision('media', 'foreground_media', owner_seconds, words, tuple(signals))
        if words < WORD_FLOOR:
            return ContentDecision('noise', 'below_floor', owner_seconds, words)
        voices = len([c for c in evidence.clusters if c.speech_seconds > 0]) if evidence else 0
        if (end - start).total_seconds() >= BYSTANDER_MIN_SECONDS and voices >= 2:
            return ContentDecision('noise', 'bystander', owner_seconds, words)
    return ContentDecision('conversation', 'speech_content', owner_seconds, words)


def _protected_from_stored_media(conversation: Any) -> bool:
    """Current user authority outranks a pre-correction content-kind snapshot.

    Reuse P2's segment-scoped roles. A manual excerpt contributes only its own
    duration, matching the classifier's owner floor; it never labels siblings.
    No evidence IO or classification write belongs on this read boundary.
    """
    if (
        value(conversation, 'sync_relevance_user_kept')
        or value(conversation, 'has_photos')
        or value(conversation, 'photos')
        or value(conversation, 'user_title')
    ):
        return True
    segments = value(conversation, 'transcript_segments', ()) or ()
    roles = speaker_role_map(segments)
    seconds = 0.0
    for segment in segments:
        if value(segment, 'speaker_label_source') != 'manual':
            continue
        role = roles.for_segment(segment).role
        if role != 'primary_user':
            if role == 'unknown' and value(segment, 'is_user') and not value(segment, 'person_id'):
                # Conflicting/unscoped manual anchors cannot grant identity,
                # but their uncertainty is not proof of owner absence either.
                return True
            continue
        start, end = value(segment, 'start'), value(segment, 'end')
        if (
            not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not math.isfinite(start)
            or not math.isfinite(end)
            or end < start
        ):
            return True  # Current owner with unknown coverage is not owner absence.
        seconds += end - start
    return seconds > OWNER_FLOOR_SECONDS


def exclude_from_derived(uid: str, conversation: Any, *, consumer: str) -> bool:
    """One check per consumer; both shadow and rollback preserve legacy behavior."""
    if not shadow_or_serve(FLAG):
        return False
    media = value(conversation, 'content_kind') in ('media', 'noise')
    protected = media and _protected_from_stored_media(conversation)
    excluded = media and not protected
    observe(consumer, 'disagree' if excluded else 'agree')
    logger.info(
        'event=media_derived_admission consumer=%s reason=%s serving=%s',
        consumer if consumer in ('memories', 'daily_summary', 'recap', 'action_items', 'notes') else 'unknown',
        'protected' if protected else value(conversation, 'content_kind') if excluded else 'eligible',
        str(serving_for(FLAG, uid)).lower(),
    )
    return excluded and serving_for(FLAG, uid)


def noise_hidden_from_home(
    uid: str, conversation: Any, *, client_supports_discarded: bool = False, user_kept: bool = False
) -> bool:
    """Reuse the existing discard projection only for a client known to support it.

    A discard is recoverable in Show discarded/history; absent capability retains
    the row's visibility. This never changes the deterministic relevance rules.
    """
    return (
        client_supports_discarded
        and not user_kept
        and value(conversation, 'content_kind') in ('media', 'noise')
        and serving_for(FLAG, uid)
    )
