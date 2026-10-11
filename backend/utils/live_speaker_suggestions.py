"""Emit and reconcile live speaker suggestions without changing identity decisions."""

from typing import Any, Optional

from models.message_event import SpeakerLabelSuggestionEvent
from utils.product_telemetry import emit_product_event
from utils.stt.speaker_match import SpeakerMatchDecision, voice_candidates
from utils.transcribe_decisions import USER_SELF_PERSON_ID, person_id_for_client


def emit_speaker_suggestion(
    host: Any,
    speaker_id: int,
    person_id: str,
    person_name: str,
    segment_id: str,
    suggested_person_id: Optional[str] = None,
    *,
    retracted: bool = False,
) -> None:
    if not retracted:
        emit_product_event(
            uid=host.request.uid,
            event='Speaker Identity Proposed',
            properties={
                'recording_id': host.recording_session_id,
                'conversation_id': host.state.current_conversation_id,
                'speaker_id': speaker_id,
                'matched_existing_person': bool(person_id),
                'auto_assign_enabled': host.request.speaker_auto_assign_enabled,
                'proposal_source': 'live_speaker_identification',
            },
        )
    host.send_event(
        SpeakerLabelSuggestionEvent(
            speaker_id=speaker_id,
            person_id=(
                'user'
                if person_id == USER_SELF_PERSON_ID
                else person_id_for_client(person_id, host.request.speaker_auto_assign_enabled)
            ),
            person_name=person_name,
            segment_id=segment_id,
            suggested_person_id=suggested_person_id,
            retracted=retracted,
        )
    )


def reconcile_pinned_suggestion(
    matcher: Any, voice: int, result: SpeakerMatchDecision, pinned: set, segment_id: str, assigned: set
) -> None:
    excluded = (
        assigned | set(matcher.segment_assignments.values()) | {pid for pid, _ in matcher.speaker_to_person.values()}
    )
    candidates = voice_candidates(
        matcher._voice_distances.get(voice, {}), result, pinned, exclude=tuple(excluded | {USER_SELF_PERSON_ID})
    )
    matcher.voice_candidates[voice] = candidates
    near = next((entry['person_id'] for entry in candidates if entry.get('suggest')), None)
    previous = matcher._suggested_person.get(voice)
    if near == previous:
        return
    if near is None:
        matcher._suggested_person.pop(voice, None)
        matcher.host.emit_speaker_suggestion(voice, '', '', segment_id, retracted=True)
    else:
        matcher._suggested_person[voice] = near
        matcher.host.emit_speaker_suggestion(
            voice, '', matcher.person_embeddings[near]['name'], segment_id, suggested_person_id=near
        )
