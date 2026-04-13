from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Sequence

from models.other import Person

if TYPE_CHECKING:
    from models.conversation import Conversation


def conversations_to_string(
    conversations: Sequence[Conversation],
    use_transcript: bool = False,
    include_timestamps: bool = False,
    people: List[Person] = None,
    user_name: str = None,
) -> str:
    """Format a sequence of Conversation objects into a human-readable string.

    Callers must pass hydrated Conversation objects (use factory.hydrate_conversation
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
    """Recursively convert datetime objects to ISO format strings.

    Replaces: models/conversation.py::as_dict_cleaned_dates (nested helper),
              utils/webhooks.py::_json_serialize_datetime,
              utils/app_integrations.py::_json_serialize_datetime.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_datetimes(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetimes(item) for item in obj]
    return obj


def conversation_to_dict(conversation: Conversation) -> Dict:
    """Convert a Conversation to a JSON-safe dict with ISO datetime strings.

    Replaces Conversation.as_dict_cleaned_dates(). Serialization is a rendering
    concern, not a model concern.
    """
    return serialize_datetimes(conversation.dict())
