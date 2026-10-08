"""Per-conversation owner-recognition outcomes and live matcher decisions.

Counters use closed label sets only. User ids and conversation ids stay on the
``owner_recognition_outcome`` log line, never on a metric label. Registration
reuses an existing collector so a harness reload does not create a duplicate
timeseries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Mapping, Optional

from prometheus_client import REGISTRY, Counter, Histogram

from models.conversation_enums import ConversationSource, ConversationStatus
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.recovery import structured_is_rich
from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL
from utils.stt.speaker_match import SPEAKER_MATCH_MIN_EVIDENCE_SECONDS, SpeakerMatchDecision
from utils.transcribe_decisions import USER_SELF_PERSON_ID

logger = logging.getLogger(__name__)

# Same floor the live matcher uses before it will accept or reject a voice.
# Shorter conversations are ``too_little_speech``, not a failed recognition.
MIN_SPEECH_SECONDS = SPEAKER_MATCH_MIN_EVIDENCE_SECONDS

SURFACES = frozenset({'live', 'sync', 'desktop', 'other'})
OUTCOMES = frozenset(
    {
        'owner_identified',
        'no_owner_profile',
        'owner_not_identified',
        'single_speaker_all_owner',
        'too_little_speech',
    }
)
_IDENTIFIED = frozenset({'owner_identified', 'single_speaker_all_owner'})
_SOURCE_VALUES = frozenset(item.value for item in ConversationSource)
_OTHER_SOURCES = frozenset({'workflow', 'external_integration', 'screenpipe', 'sdcard', 'unknown'})
_SYNC_PREFIXES = ('sync:', 'legacy-conversation:')
_RESOLUTION_STATUS = frozenset({'resolved', 'capture', 'unavailable'})
_TARGETS = frozenset({'owner', 'person'})
_LIVE_DECISIONS = frozenset({'accepted', 'rejected', 'ambiguous', 'pending'})
_CARRIED = frozenset({'manual', 'automatic', 'none'})
# process_conversation stamps one of these on relevance_decision.trigger.
# Sync intake stamps ``sync_intake`` or nothing, which is not in this set.
_PROCESSED_TRIGGERS = frozenset(item.value for item in ProcessingTrigger)


def _owner_recognition_conversations() -> Counter:
    try:
        return Counter(
            'omi_owner_recognition_conversations_total',
            'Finalized conversations by capture surface, conversation source, and owner-recognition outcome',
            ['surface', 'source', 'outcome'],
        )
    except ValueError:
        return REGISTRY._names_to_collectors['omi_owner_recognition_conversations_total']  # type: ignore[attr-defined]


def _owner_recognition_owner_share() -> Histogram:
    try:
        return Histogram(
            'omi_owner_recognition_owner_share',
            'Owner-labeled share of speech seconds on conversations where the owner was identified',
            buckets=(0.1, 0.25, 0.5, 0.75, 0.9, 1.0),
        )
    except ValueError:
        return REGISTRY._names_to_collectors['omi_owner_recognition_owner_share']  # type: ignore[attr-defined]


def _live_speaker_decisions() -> Counter:
    try:
        return Counter(
            'omi_speaker_id_live_decisions_total',
            'Live voiceprint decisions by enrolled target and accept, reject, ambiguous, or pending',
            ['target', 'decision'],
        )
    except ValueError:
        return REGISTRY._names_to_collectors['omi_speaker_id_live_decisions_total']  # type: ignore[attr-defined]


def _live_speaker_rollover() -> Counter:
    try:
        return Counter(
            'omi_live_speaker_rollover_total',
            'Speakers the live matcher had mapped when a same-stream conversation rolled over',
            ['carried', 'target'],
        )
    except ValueError:
        return REGISTRY._names_to_collectors['omi_live_speaker_rollover_total']  # type: ignore[attr-defined]


OWNER_RECOGNITION_CONVERSATIONS = _owner_recognition_conversations()
OWNER_RECOGNITION_OWNER_SHARE = _owner_recognition_owner_share()
LIVE_SPEAKER_DECISIONS = _live_speaker_decisions()
LIVE_SPEAKER_ROLLOVER = _live_speaker_rollover()

for _target in ('owner', 'person'):
    for _decision in ('accepted', 'rejected', 'ambiguous', 'pending'):
        LIVE_SPEAKER_DECISIONS.labels(target=_target, decision=_decision)
for _carried in ('manual', 'automatic', 'none'):
    for _target in ('owner', 'person'):
        LIVE_SPEAKER_ROLLOVER.labels(carried=_carried, target=_target)


def _field(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def _segments(conversation: Any) -> list[Any]:
    raw = _field(conversation, 'transcript_segments')
    if not raw:
        return []
    return list(raw)


def _duration(segment: Any) -> float:
    try:
        start = float(_field(segment, 'start'))
        end = float(_field(segment, 'end'))
    except (TypeError, ValueError):
        return 0.0
    if not isfinite(start) or not isfinite(end) or end <= start:
        return 0.0
    return end - start


@dataclass(frozen=True)
class SpeechStats:
    total_seconds: float
    owner_seconds: float
    speech_segments: int
    owner_segments: int
    distinct_speakers: int

    @property
    def owner_share(self) -> float:
        if self.total_seconds <= 0:
            return 0.0
        return min(1.0, self.owner_seconds / self.total_seconds)


def speech_stats(conversation: Any) -> SpeechStats:
    total = 0.0
    owner = 0.0
    speech_segments = 0
    owner_segments = 0
    speakers: set[int] = set()
    for segment in _segments(conversation):
        duration = _duration(segment)
        if duration <= 0:
            continue
        speech_segments += 1
        total += duration
        if bool(_field(segment, 'is_user')):
            owner += duration
            owner_segments += 1
        speaker_id = _field(segment, 'speaker_id')
        if isinstance(speaker_id, int) and speaker_id != OMI_SPEAKER_ID_SENTINEL:
            speakers.add(speaker_id)
    return SpeechStats(total, owner, speech_segments, owner_segments, len(speakers))


def source_label(conversation: Any) -> str:
    raw = _field(conversation, 'source')
    if raw is None:
        return 'unknown'
    value = getattr(raw, 'value', raw)
    text = str(value)
    return text if text in _SOURCE_VALUES else 'other'


def surface_label(conversation: Any) -> str:
    """live, sync, desktop, or other.

    Desktop source wins. Otherwise a ``sync:`` or ``legacy-conversation:`` scope
    is sync, and any other scope is live (a mixed conversation counts as live).
    With no scopes, device sources are live and non-capture sources are other.
    """
    source = source_label(conversation)
    if source == 'desktop':
        return 'desktop'
    scopes = [
        scope
        for scope in (_field(segment, 'speaker_id_scope') for segment in _segments(conversation))
        if isinstance(scope, str) and scope
    ]
    if scopes:
        if any(not scope.startswith(_SYNC_PREFIXES) for scope in scopes):
            return 'live'
        return 'sync'
    if source in _OTHER_SOURCES:
        return 'other'
    return 'live'


def classify_owner_recognition(stats: SpeechStats, *, owner_profile_present: Optional[bool]) -> Optional[str]:
    """One closed outcome, or None when the profile lookup failed and we would have to guess."""
    if stats.speech_segments == 0 or stats.total_seconds < MIN_SPEECH_SECONDS:
        return 'too_little_speech'
    if stats.owner_segments == stats.speech_segments:
        return 'single_speaker_all_owner'
    if stats.owner_segments >= 1:
        return 'owner_identified'
    if owner_profile_present is None:
        return None
    if not owner_profile_present:
        return 'no_owner_profile'
    return 'owner_not_identified'


def owner_recognition_needs_profile(conversation: Any) -> bool:
    """True only when no segment is the owner and there is enough speech to judge."""
    stats = speech_stats(conversation)
    if stats.speech_segments == 0 or stats.total_seconds < MIN_SPEECH_SECONDS:
        return False
    return stats.owner_segments == 0


def lookup_owner_voiceprint(uid: str, *, read_embedding: Callable[[str], Any]) -> Optional[bool]:
    """Whether the account has an owner voiceprint. None means the read failed."""
    try:
        return bool(read_embedding(uid))
    except Exception:
        logger.warning('owner_recognition_outcome profile_lookup_failed uid=%s', uid)
        return None


def _resolution_status(conversation: Any) -> str:
    resolution = _field(conversation, 'speaker_resolution')
    status = _field(resolution, 'status') if resolution is not None else None
    if status in _RESOLUTION_STATUS:
        return str(status)
    return 'absent'


def _log_outcome(
    conversation: Any,
    *,
    uid: str,
    surface: str,
    source: str,
    outcome: str,
    stats: SpeechStats,
    counted: bool,
) -> None:
    logger.info(
        'owner_recognition_outcome uid=%s conversation=%s surface=%s source=%s outcome=%s '
        'speakers=%s owner_speech_seconds=%.3f total_speech_seconds=%.3f '
        'speaker_match_scores=%s speaker_resolution_status=%s counted=%s',
        uid,
        _field(conversation, 'id'),
        surface,
        source,
        outcome,
        stats.distinct_speakers,
        stats.owner_seconds,
        stats.total_seconds,
        bool(_field(conversation, 'speaker_match_scores')),
        _resolution_status(conversation),
        counted,
    )


def _relevance_trigger(decision: Any) -> Optional[str]:
    if not isinstance(decision, Mapping):
        return None
    trigger = decision.get('trigger')
    return trigger if isinstance(trigger, str) else None


def _status_value(conversation: Any) -> Optional[str]:
    status = _field(conversation, 'status')
    value = getattr(status, 'value', status)
    return value if isinstance(value, str) else None


def _enriched_or_terminal(conversation: Any) -> bool:
    """True when an earlier pass already enriched this row or stored a free-tier terminal.

    The deterministic minimum leaves overview, sections, action items, and events
    empty, so ``structured_is_rich`` is false until enrichment. A bare minimum
    sets ``processing_state``. ``client_processing`` is not that evidence:
    ingress can attach a projection to a deferred, still-processing row whose
    capture never emitted.
    """
    if structured_is_rich(_field(conversation, 'structured')):
        return True
    return _field(conversation, 'processing_state') is not None


def owner_recognition_already_observed(
    conversation: Any,
    *,
    is_reprocess: bool,
    trigger: ProcessingTrigger,
    prior_relevance_decision: Any = None,
) -> bool:
    """Whether this call would be a second observation of the same conversation.

    Sync intake persists ``status=completed`` before the first ``SYNC_UPDATE``,
    and clears ``discarded`` when later speech promotes a fragment. Completed
    status is intake's, not an observation. A previous ``process_conversation``
    pass stores ``relevance_decision.trigger`` as a processing trigger; intake
    stores ``sync_intake`` or nothing, and promotion deletes a rule discard.
    """
    if not is_reprocess:
        return False
    if _enriched_or_terminal(conversation):
        return True
    if trigger is ProcessingTrigger.SYNC_UPDATE:
        return _relevance_trigger(prior_relevance_decision) in _PROCESSED_TRIGGERS
    return _status_value(conversation) == ConversationStatus.completed.value


def emit_finalized_owner_recognition(
    conversation: Any,
    *,
    uid: str,
    already_observed: bool,
    owner_profile_present: Optional[bool],
) -> Optional[str]:
    """Count one finalized transcript. An already-enriched row does not count again.

    Returns the outcome when the counter moved.
    """
    if already_observed:
        return None
    stats = speech_stats(conversation)
    surface = surface_label(conversation)
    source = source_label(conversation)
    outcome = classify_owner_recognition(stats, owner_profile_present=owner_profile_present)
    if outcome is None:
        _log_outcome(
            conversation,
            uid=uid,
            surface=surface,
            source=source,
            outcome='profile_lookup_failed',
            stats=stats,
            counted=False,
        )
        return None
    if surface not in SURFACES:
        surface = 'other'
    if outcome not in OUTCOMES:
        outcome = 'owner_not_identified'
    OWNER_RECOGNITION_CONVERSATIONS.labels(surface=surface, source=source, outcome=outcome).inc()
    if outcome in _IDENTIFIED and stats.total_seconds > 0:
        OWNER_RECOGNITION_OWNER_SHARE.observe(stats.owner_share)
    _log_outcome(
        conversation,
        uid=uid,
        surface=surface,
        source=source,
        outcome=outcome,
        stats=stats,
        counted=True,
    )
    return outcome


def record_live_speaker_decision(target: str, decision: str) -> None:
    try:
        if target not in _TARGETS:
            target = 'person'
        if decision not in _LIVE_DECISIONS:
            decision = 'rejected'
        LIVE_SPEAKER_DECISIONS.labels(target=target, decision=decision).inc()
    except Exception:
        logger.warning('speaker_id_live_decision_record_failed')


def pending_decision_target(*, owner_enrolled: bool) -> str:
    """Pending evidence has no winner yet. The enrolled owner is the target when that print is loaded."""
    return 'owner' if owner_enrolled else 'person'


def live_decision_labels(decision: SpeakerMatchDecision, *, owner_enrolled: bool) -> tuple[str, str]:
    if decision.owner_contended:
        return 'owner', 'ambiguous'
    if decision.person_id is not None:
        target = 'owner' if decision.person_id == USER_SELF_PERSON_ID else 'person'
        return target, 'accepted'
    if decision.best_id == USER_SELF_PERSON_ID or (decision.best_id is None and owner_enrolled):
        return 'owner', 'rejected'
    return 'person', 'rejected'


def record_live_speaker_rollover(
    mappings: Mapping[int, Any],
    origins: Mapping[int, str],
    carried_speaker_ids: Optional[set[int]],
) -> None:
    """Count mappings about to be cleared. Automatic ones are not carried today.

    ``carried_speaker_ids`` is the receipt's carried speaker ids. None is the
    unreported case: a manual origin counts as carried and every automatic
    mapping as dropped. The live rollover path does not use None; it passes the
    receipt set, including an empty one when nobody was copied.
    """
    try:
        for speaker_id, identity in mappings.items():
            person_id = identity[0] if identity else None
            target = 'owner' if person_id == USER_SELF_PERSON_ID else 'person'
            if target not in _TARGETS:
                target = 'person'
            origin = origins.get(speaker_id, 'automatic')
            if carried_speaker_ids is None:
                carried = 'manual' if origin == 'manual' else 'none'
            elif speaker_id in carried_speaker_ids and origin == 'automatic':
                carried = 'automatic'
            elif speaker_id in carried_speaker_ids:
                carried = 'manual'
            else:
                carried = 'none'
            if carried not in _CARRIED:
                carried = 'none'
            LIVE_SPEAKER_ROLLOVER.labels(carried=carried, target=target).inc()
    except Exception:
        logger.warning('live_speaker_rollover_record_failed')
