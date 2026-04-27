from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Sequence

import database.folders as folders_db
import database.users as users_db
from models.other import Person

if TYPE_CHECKING:
    from models.conversation import Conversation


# ---------------------------------------------------------------------------
# Populate: speaker names, folder names
# ---------------------------------------------------------------------------


def populate_speaker_names(uid: str, conversations: List[Dict]) -> None:
    """Add speaker_name to transcript segments based on person_id mappings.

    Mutates conversation dicts in-place. Works with both single conversations
    (pass as [conv]) and lists.
    """
    user_profile = users_db.get_user_profile(uid)
    user_name = user_profile.get('name') or 'User'

    all_person_ids = set()
    for conv in conversations:
        for seg in conv.get('transcript_segments', []):
            if seg.get('person_id'):
                all_person_ids.add(seg['person_id'])

    people_map = {}
    if all_person_ids:
        people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
        people_map = {p['id']: p['name'] for p in people_data}

    for conv in conversations:
        for seg in conv.get('transcript_segments', []):
            if seg.get('is_user'):
                seg['speaker_name'] = user_name
            elif seg.get('person_id') and seg['person_id'] in people_map:
                seg['speaker_name'] = people_map[seg['person_id']]
            else:
                seg['speaker_name'] = f"Speaker {seg.get('speaker_id', 0)}"


def populate_folder_names(uid: str, conversations: List[Dict]) -> None:
    """Add folder_name to conversations based on folder_id mappings.

    Mutates conversation dicts in-place. Batch-loads all folder IDs in one query.
    """
    folder_ids = set()
    for conv in conversations:
        if conv.get('folder_id'):
            folder_ids.add(conv['folder_id'])

    if not folder_ids:
        for conv in conversations:
            conv['folder_name'] = None
        return

    all_folders = folders_db.get_folders(uid)
    folder_map = {f['id']: f['name'] for f in all_folders}

    for conv in conversations:
        folder_id = conv.get('folder_id')
        conv['folder_name'] = folder_map.get(folder_id) if folder_id else None


# ---------------------------------------------------------------------------
# Redact: locked-content stripping
# ---------------------------------------------------------------------------


def redact_conversation_for_list(conv: Dict) -> Dict:
    """Standard list-view redaction: strip detail fields, keep title/overview."""
    if not conv.get('is_locked', False):
        return conv
    if 'structured' in conv:
        conv['structured'] = (
            dict(conv['structured']) if not isinstance(conv['structured'], dict) else conv['structured']
        )
        conv['structured']['action_items'] = []
        conv['structured']['events'] = []
    conv['apps_results'] = []
    conv['plugins_results'] = []
    conv['suggested_summarization_apps'] = []
    conv['transcript_segments'] = []
    return conv


def redact_conversation_for_integration(conv: Dict) -> Dict:
    """Integration-view redaction: strip everything including title/overview."""
    if not conv.get('is_locked', False):
        return conv
    if 'structured' in conv:
        conv['structured'] = (
            dict(conv['structured']) if not isinstance(conv['structured'], dict) else conv['structured']
        )
        conv['structured']['title'] = ''
        conv['structured']['overview'] = ''
        conv['structured']['action_items'] = []
        conv['structured']['events'] = []
    conv['apps_results'] = []
    conv['plugins_results'] = []
    conv['suggested_summarization_apps'] = []
    conv['transcript_segments'] = []
    return conv


def redact_conversations_for_list(conversations: List[Dict]) -> List[Dict]:
    """Apply standard list redaction to a batch of conversations."""
    return [redact_conversation_for_list(c) for c in conversations]


def redact_conversations_for_integration(conversations: List[Dict]) -> List[Dict]:
    """Apply integration redaction to a batch of conversations."""
    return [redact_conversation_for_integration(c) for c in conversations]


# ---------------------------------------------------------------------------
# Serialize: datetime handling, dict conversion
# ---------------------------------------------------------------------------


def conversations_to_string(
    conversations: Sequence[Conversation],
    use_transcript: bool = False,
    include_timestamps: bool = False,
    people: List[Person] = None,
    user_name: str = None,
) -> str:
    """Format a sequence of Conversation objects into a human-readable string.

    Callers must pass deserialized Conversation objects (use factory.deserialize_conversation
    for raw dicts). This function does NOT accept dicts.
    """
    result = []
    people_map = {p.id: p for p in people} if people else {}
    for i, conversation in enumerate(conversations):
        formatted_date = conversation.created_at.astimezone(timezone.utc).strftime("%d %b %Y at %H:%M") + " UTC"
        conversation_str = (
            f"Conversation #{i + 1}\n"
            f"{formatted_date} ({str(conversation.structured.category.value).capitalize()})\n"
        )

        # Add started_at and finished_at if available
        if conversation.started_at:
            formatted_started = conversation.started_at.astimezone(timezone.utc).strftime("%d %b %Y at %H:%M") + " UTC"
            conversation_str += f"Started: {formatted_started}\n"
        if conversation.finished_at:
            formatted_finished = (
                conversation.finished_at.astimezone(timezone.utc).strftime("%d %b %Y at %H:%M") + " UTC"
            )
            conversation_str += f"Finished: {formatted_finished}\n"

        conversation_str += f"{str(conversation.structured.title).capitalize()}\n"

        if (
            conversation.apps_results
            and len(conversation.apps_results) > 0
            and conversation.apps_results[0].content.strip()
        ):
            conversation_str += f"{conversation.apps_results[0].content}\n"
        else:
            conversation_str += f"{str(conversation.structured.overview).capitalize()}\n"

        # attendees
        if people_map:
            conv_person_ids = set(conversation.get_person_ids())
            if conv_person_ids:
                attendees_names = [people_map[pid].name for pid in conv_person_ids if pid in people_map]
                if attendees_names:
                    attendees = ", ".join(attendees_names)
                    conversation_str += f"Attendees: {attendees}\n"

        if conversation.structured.action_items:
            conversation_str += "Action Items:\n"
            for item in conversation.structured.action_items:
                conversation_str += f"- {item.description}\n"

        if conversation.structured.events:
            conversation_str += "Events:\n"
            for event in conversation.structured.events:
                conversation_str += f"- {event.title} ({event.start} - {event.duration} minutes)\n"

        if use_transcript:
            conversation_str += f"\nTranscript:\n{conversation.get_transcript(include_timestamps=include_timestamps, people=people, user_name=user_name)}\n"
            # photos
            photo_descriptions = conversation.get_photos_descriptions(include_timestamps=include_timestamps)
            if photo_descriptions != 'None':
                conversation_str += f"Photo Descriptions from a wearable camera:\n{photo_descriptions}\n"

        result.append(conversation_str.strip())

    return "\n\n---------------------\n\n".join(result).strip()


def serialize_datetimes(obj: Any) -> Any:
    """Recursively convert datetime objects to ISO format strings."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_datetimes(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetimes(item) for item in obj]
    return obj


def conversation_to_dict(conversation: Conversation) -> Dict:
    """Convert a Conversation to a JSON-safe dict with ISO datetime strings."""
    return serialize_datetimes(conversation.dict())
