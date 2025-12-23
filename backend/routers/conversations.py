from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import Optional, List
from datetime import datetime, timezone

import database.conversations as conversations_db
import database.action_items as action_items_db
import database.redis_db as redis_db
import database.users as users_db
from database.vector_db import delete_vector
from models.conversation import (
    BaseModel,
    CalendarEventLink,
    CalendarMeetingContext,
    Conversation,
    ConversationPhoto,
    ConversationStatus,
    ConversationVisibility,
    CreateConversationResponse,
    MergeConversationsRequest,
    MergeConversationsResponse,
    SetConversationEventsStateRequest,
    SetConversationActionItemsStateRequest,
    UpdateActionItemDescriptionRequest,
    DeleteActionItemRequest,
    BulkAssignSegmentsRequest,
    SearchRequest,
    TestPromptRequest,
)
from models.transcript_segment import TranscriptSegment
from models.other import Person

from utils.conversations.process_conversation import process_conversation, retrieve_in_progress_conversation
from utils.conversations.search import search_conversations
from utils.llm.conversation_processing import generate_summary_with_prompt
from utils.other import endpoints as auth
from utils.other.storage import get_conversation_recording_if_exists
from utils.app_integrations import trigger_external_integrations
from utils.retrieval.tools.calendar_tools import get_google_calendar_event, update_google_calendar_event
from utils.retrieval.tools.google_utils import refresh_google_token
from utils.conversations.calendar_linking import get_overlapping_calendar_event

router = APIRouter()


def _get_valid_conversation_by_id(uid: str, conversation_id: str) -> dict:
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="Unlimited Plan Required to access this conversation.")

    return conversation


class ProcessConversationRequest(BaseModel):
    calendar_meeting_context: Optional[CalendarMeetingContext] = None


@router.post("/v1/conversations", response_model=CreateConversationResponse, tags=['conversations'])
def process_in_progress_conversation(
    request: ProcessConversationRequest = None, uid: str = Depends(auth.get_current_user_uid)
):
    conversation = retrieve_in_progress_conversation(uid)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation in progress not found")
    redis_db.remove_in_progress_conversation_id(uid)

    conversation = Conversation(**conversation)

    # Inject calendar context if provided
    if request and request.calendar_meeting_context:
        if not conversation.external_data:
            conversation.external_data = {}
        conversation.external_data['calendar_meeting_context'] = request.calendar_meeting_context.dict()

    conversations_db.update_conversation_status(uid, conversation.id, ConversationStatus.processing)
    conversation = process_conversation(uid, conversation.language, conversation, force_process=True)
    messages = trigger_external_integrations(uid, conversation)

    return CreateConversationResponse(conversation=conversation, messages=messages)


@router.post('/v1/conversations/{conversation_id}/reprocess', response_model=Conversation, tags=['conversations'])
def reprocess_conversation(
    conversation_id: str,
    language_code: Optional[str] = None,
    app_id: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Whenever a user wants to reprocess a conversation, or wants to force process a discarded one
    :param conversation_id: The ID of the conversation to reprocess
    :param language_code: Optional language code to use for processing
    :param app_id: Optional app ID to use for processing (if provided, only this app will be triggered)
    :return: The updated conversation after reprocessing.
    """
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)
    if not language_code:
        language_code = conversation.language or 'en'

    processed_conversation = process_conversation(
        uid, language_code, conversation, force_process=True, is_reprocess=True, app_id=app_id
    )

    return processed_conversation


@router.get('/v1/conversations', response_model=List[Conversation], tags=['conversations'])
def get_conversations(
    limit: int = 100,
    offset: int = 0,
    statuses: Optional[str] = "processing,completed",
    include_discarded: bool = True,
    start_date: Optional[datetime] = Query(None, description="Filter by start date (inclusive)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (inclusive)"),
    uid: str = Depends(auth.get_current_user_uid),
):
    print('get_conversations', uid, limit, offset, statuses)
    # force convos statuses to processing, completed on the empty filter
    if len(statuses) == 0:
        statuses = "processing,completed"

    conversations = conversations_db.get_conversations(
        uid,
        limit,
        offset,
        include_discarded=include_discarded,
        statuses=statuses.split(",") if len(statuses) > 0 else [],
        start_date=start_date,
        end_date=end_date,
    )

    for conv in conversations:
        if conv.get('is_locked', False):
            conv['structured']['action_items'] = []
            conv['structured']['events'] = []
            conv['apps_results'] = []
            conv['plugins_results'] = []
            conv['suggested_summarization_apps'] = []
    return conversations


@router.get("/v1/conversations/{conversation_id}", response_model=Conversation, tags=['conversations'])
def get_conversation_by_id(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    print('get_conversation_by_id', uid, conversation_id)
    return _get_valid_conversation_by_id(uid, conversation_id)


@router.patch("/v1/conversations/{conversation_id}/title", tags=['conversations'])
def patch_conversation_title(conversation_id: str, title: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_valid_conversation_by_id(uid, conversation_id)
    conversations_db.update_conversation_title(uid, conversation_id, title)
    return {'status': 'Ok'}


@router.delete("/v1/conversations/{conversation_id}/calendar-event", tags=['conversations'])
def unlink_calendar_event(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Unlink a calendar event from a conversation.
    This removes the calendar_event field from the conversation.
    """
    _get_valid_conversation_by_id(uid, conversation_id)
    conversations_db.update_conversation(uid, conversation_id, {'calendar_event': None})
    return {'status': 'Ok'}


class LinkCalendarEventRequest(BaseModel):
    event_id: str


def _extract_attendees(event: dict) -> tuple[list[str], list[str]]:
    """Extract attendee names and emails from a Google Calendar event."""
    names = []
    emails = []
    for attendee in event.get('attendees', []):
        if attendee.get('self', False):
            continue
        email = attendee.get('email', '')
        name = attendee.get('displayName') or email
        if name:
            names.append(name)
        if email:
            emails.append(email)
    return names, emails


def _parse_event_times(event: dict) -> tuple[Optional[datetime], Optional[datetime]]:
    """Parse start and end times from a Google Calendar event."""
    start = event.get('start', {})
    end = event.get('end', {})
    try:
        if 'dateTime' in start:
            start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
        elif 'date' in start:
            start_dt = datetime.fromisoformat(start['date'] + 'T00:00:00+00:00')
        else:
            return None, None

        if 'dateTime' in end:
            end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
        elif 'date' in end:
            end_dt = datetime.fromisoformat(end['date'] + 'T23:59:59+00:00')
        else:
            return None, None

        return start_dt, end_dt
    except (ValueError, KeyError):
        return None, None


def _event_to_calendar_event_link(event: dict) -> Optional[CalendarEventLink]:
    """Convert a raw Google Calendar event to CalendarEventLink model."""
    start_time, end_time = _parse_event_times(event)
    if start_time is None or end_time is None:
        return None

    attendee_names, attendee_emails = _extract_attendees(event)

    return CalendarEventLink(
        event_id=event.get('id', ''),
        title=event.get('summary', 'Untitled Event'),
        attendees=attendee_names,
        attendee_emails=attendee_emails,
        start_time=start_time,
        end_time=end_time,
        html_link=event.get('htmlLink'),
    )


@router.post(
    "/v1/conversations/{conversation_id}/calendar-event", response_model=CalendarEventLink, tags=['conversations']
)
def link_calendar_event(
    conversation_id: str,
    request: LinkCalendarEventRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Link a specific Google Calendar event to an existing conversation.
    Fetches the event details and stores the calendar_event on the conversation.
    """
    _get_valid_conversation_by_id(uid, conversation_id)

    # Get Google Calendar access token
    integration = users_db.get_integration(uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        raise HTTPException(status_code=400, detail="Google Calendar not connected")

    access_token = integration.get('access_token')
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token found")

    # Fetch the event from Google Calendar
    try:
        event = get_google_calendar_event(access_token, request.event_id)
    except Exception as e:
        error_msg = str(e)
        # Try to refresh token if authentication failed
        if "Authentication failed" in error_msg or "401" in error_msg:
            new_token = refresh_google_token(uid, integration)
            if new_token:
                try:
                    event = get_google_calendar_event(new_token, request.event_id)
                except Exception as retry_error:
                    raise HTTPException(status_code=500, detail=f"Failed after token refresh: {str(retry_error)}")
            else:
                raise HTTPException(status_code=401, detail="Google Calendar authentication expired. Please reconnect.")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch calendar event: {error_msg}")

    # Convert to CalendarEventLink
    calendar_event = _event_to_calendar_event_link(event)
    if calendar_event is None:
        raise HTTPException(status_code=400, detail="Could not parse calendar event times")

    # Persist to Firestore
    conversations_db.update_conversation(uid, conversation_id, {'calendar_event': calendar_event.dict()})

    return calendar_event


@router.post(
    "/v1/conversations/{conversation_id}/calendar-event/auto-link",
    response_model=CalendarEventLink,
    tags=['conversations'],
)
def auto_link_calendar_event(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Auto-link a conversation to the best overlapping Google Calendar event.
    Uses the conversation's started_at/finished_at to find a matching event.
    Returns 404 if no overlapping event is found.
    """
    conversation = _get_valid_conversation_by_id(uid, conversation_id)

    # Get conversation times
    started_at = conversation.get('started_at')
    finished_at = conversation.get('finished_at')

    # Fall back to created_at if times are not available
    if not started_at:
        started_at = conversation.get('created_at')
    if not finished_at:
        finished_at = started_at

    if not started_at:
        raise HTTPException(status_code=400, detail="Conversation has no timestamp information")

    # Parse datetimes if they're strings
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
    if isinstance(finished_at, str):
        finished_at = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))

    # Ensure timezone-aware
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)

    # Find overlapping calendar event
    calendar_event = get_overlapping_calendar_event(uid, started_at, finished_at)

    if calendar_event is None:
        raise HTTPException(status_code=404, detail="No overlapping calendar event found")

    # Persist to Firestore
    conversations_db.update_conversation(uid, conversation_id, {'calendar_event': calendar_event.dict()})

    return calendar_event


def _add_summary_to_calendar_event_with_token(
    access_token: str,
    event_id: str,
    conversation_id: str,
) -> dict:
    """Helper function to add summary link to calendar event with given token."""
    # Get existing event to preserve current description
    existing_event = get_google_calendar_event(access_token, event_id)
    current_description = existing_event.get('description', '') or ''

    # Build the conversation link
    conversation_link = f"https://h.omi.me/memories/{conversation_id}"

    # Check if we already added the link (to avoid duplicates)
    if conversation_link in current_description:
        return {
            'status': 'Ok',
            'html_link': existing_event.get('htmlLink'),
        }

    # Append just the link
    if current_description:
        new_description = f"{current_description}\n\n{conversation_link}"
    else:
        new_description = conversation_link

    # Update the calendar event
    updated_event = update_google_calendar_event(
        access_token=access_token,
        event_id=event_id,
        description=new_description,
    )

    return {
        'status': 'Ok',
        'html_link': updated_event.get('htmlLink'),
    }


@router.post("/v1/conversations/{conversation_id}/calendar-event/add-summary", tags=['conversations'])
def add_summary_to_calendar_event(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Add conversation summary to the linked calendar event description.
    """
    conversation = _get_valid_conversation_by_id(uid, conversation_id)

    calendar_event = conversation.get('calendar_event')
    if not calendar_event:
        raise HTTPException(status_code=400, detail="No calendar event linked to this conversation")

    event_id = calendar_event.get('event_id')
    if not event_id:
        raise HTTPException(status_code=400, detail="Calendar event ID not found")

    # Get Google Calendar access token
    integration = users_db.get_integration(uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        raise HTTPException(status_code=400, detail="Google Calendar not connected")

    access_token = integration.get('access_token')
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token found")

    try:
        return _add_summary_to_calendar_event_with_token(access_token, event_id, conversation_id)
    except Exception as e:
        error_msg = str(e)

        # Try to refresh token if authentication failed
        if "401" in error_msg or "Authentication" in error_msg.lower():
            new_token = refresh_google_token(uid, integration)
            if new_token:
                try:
                    return _add_summary_to_calendar_event_with_token(new_token, event_id, conversation_id)
                except Exception as retry_error:
                    raise HTTPException(status_code=500, detail=f"Failed after token refresh: {str(retry_error)}")

        raise HTTPException(status_code=500, detail=f"Failed to update calendar event: {error_msg}")


@router.get(
    "/v1/conversations/{conversation_id}/photos", response_model=List[ConversationPhoto], tags=['conversations']
)
def get_conversation_photos(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_valid_conversation_by_id(uid, conversation_id)
    return conversations_db.get_conversation_photos(uid, conversation_id)


@router.get(
    "/v1/conversations/{conversation_id}/transcripts",
    response_model=dict[str, List[TranscriptSegment]],
    tags=['conversations'],
)
def get_conversation_transcripts_by_models(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_valid_conversation_by_id(uid, conversation_id)
    return conversations_db.get_conversation_transcripts_by_model(uid, conversation_id)


@router.delete("/v1/conversations/{conversation_id}", status_code=204, tags=['conversations'])
def delete_conversation(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    print('delete_conversation', conversation_id, uid)
    conversations_db.delete_conversation(uid, conversation_id)
    delete_vector(uid, conversation_id)
    return {"status": "Ok"}


@router.get("/v1/conversations/{conversation_id}/recording", response_model=dict, tags=['conversations'])
def conversation_has_audio_recording(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_valid_conversation_by_id(uid, conversation_id)
    return {'has_recording': get_conversation_recording_if_exists(uid, conversation_id) is not None}


@router.patch("/v1/conversations/{conversation_id}/events", response_model=dict, tags=['conversations'])
def set_conversation_events_state(
    conversation_id: str, data: SetConversationEventsStateRequest, uid: str = Depends(auth.get_current_user_uid)
):
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)
    events = conversation.structured.events
    for i, event_idx in enumerate(data.events_idx):
        if event_idx >= len(events):
            continue
        events[event_idx].created = data.values[i]

    conversations_db.update_conversation_events(uid, conversation_id, [event.dict() for event in events])
    return {"status": "Ok"}


@router.patch("/v1/conversations/{conversation_id}/action-items", response_model=dict, tags=['conversations'])
def set_action_item_status(
    data: SetConversationActionItemsStateRequest, conversation_id: str, uid=Depends(auth.get_current_user_uid)
):
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)
    action_items = conversation.structured.action_items
    for i, action_item_idx in enumerate(data.items_idx):
        if action_item_idx >= len(action_items):
            continue

        action_item = action_items[action_item_idx]
        new_completed_status = data.values[i]

        # Set completed status
        action_item.completed = new_completed_status

        # Handle created_at backwards compatibility
        if action_item.created_at is None:
            action_item.created_at = conversation.created_at

        # Set completed_at timestamp
        if new_completed_status:
            # Mark as completed - set completed_at to current time
            action_item.completed_at = datetime.now(timezone.utc)
        else:
            # Mark as incomplete - clear completed_at
            action_item.completed_at = None

    conversations_db.update_conversation_action_items(
        uid, conversation_id, [action_item.dict() for action_item in action_items]
    )

    # Mirror status updates to the standalone action_items collection
    try:
        existing_items = action_items_db.get_action_items_by_conversation(uid, conversation_id)
        # Map descriptions to item IDs for quick lookup
        description_to_ids = {}
        for ai in existing_items:
            desc = ai.get('description')
            if not desc:
                continue
            description_to_ids.setdefault(desc, []).append(ai['id'])

        for i, action_item_idx in enumerate(data.items_idx):
            if action_item_idx >= len(action_items):
                continue
            action_item = action_items[action_item_idx]
            new_completed_status = data.values[i]

            ids = description_to_ids.get(action_item.description, [])
            for action_item_id in ids:
                action_items_db.mark_action_item_completed(uid, action_item_id, bool(new_completed_status))
    except Exception as e:
        # Don't break conversation route if mirrored update fails
        print('Failed to mirror action item status update:', e)
    return {"status": "Ok"}


@router.patch(
    "/v1/conversations/{conversation_id}/action-items/{action_item_idx}", response_model=dict, tags=['conversations']
)
def update_action_item_description(
    conversation_id: str, data: UpdateActionItemDescriptionRequest, uid=Depends(auth.get_current_user_uid)
):
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)
    action_items = conversation.structured.action_items

    found_item = False
    for item in action_items:
        if item.description == data.old_description:
            item.description = data.description
            found_item = True
            break

    if not found_item:
        raise HTTPException(status_code=404, detail=f"Action item with description '{data.old_description}' not found")

    conversations_db.update_conversation_action_items(
        uid, conversation_id, [action_item.dict() for action_item in action_items]
    )

    # Mirror description update in the standalone action_items collection
    try:
        existing_items = action_items_db.get_action_items_by_conversation(uid, conversation_id)
        for ai in existing_items:
            if ai.get('description') == data.old_description:
                action_items_db.update_action_item(uid, ai['id'], {'description': data.description})
    except Exception as e:
        print('Failed to mirror action item description update:', e)
    return {"status": "Ok"}


@router.delete("/v1/conversations/{conversation_id}/action-items", response_model=dict, tags=['conversations'])
def delete_action_item(data: DeleteActionItemRequest, conversation_id: str, uid=Depends(auth.get_current_user_uid)):
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)
    action_items = conversation.structured.action_items
    updated_action_items = [item for item in action_items if not (item.description == data.description)]
    conversations_db.update_conversation_action_items(
        uid, conversation_id, [action_item.dict() for action_item in updated_action_items]
    )

    # Mirror deletion in the standalone action_items collection
    try:
        existing_items = action_items_db.get_action_items_by_conversation(uid, conversation_id)
        for ai in existing_items:
            if ai.get('description') == data.description:
                action_items_db.delete_action_item(uid, ai['id'])
    except Exception as e:
        print('Failed to mirror action item deletion:', e)
    return {"status": "Ok"}


@router.patch(
    '/v1/conversations/{conversation_id}/segments/{segment_idx}/assign',
    response_model=Conversation,
    tags=['conversations'],
)
def set_assignee_conversation_segment(
    conversation_id: str,
    segment_idx: int,
    assign_type: str,
    value: Optional[str] = None,
    use_for_speech_training: bool = True,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Another complex endpoint.

    Modify the assignee of a segment in the transcript of a conversation.
    But,
    if `use_for_speech_training` is True, the corresponding audio segment will be used for speech training.

    Speech training of whom?

    If `assign_type` is 'is_user', the segment will be used for the user speech training.
    If `assign_type` is 'person_id', the segment will be used for the person with the given id speech training.

    What is required for a segment to be used for speech training?
    1. The segment must have more than 5 words.
    2. The conversation audio file shuold be already stored in the user's bucket.

    :return: The updated conversation.
    """
    print(
        'set_assignee_conversation_segment',
        conversation_id,
        segment_idx,
        assign_type,
        value,
        use_for_speech_training,
        uid,
    )
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)

    if value == 'null':
        value = None

    is_unassigning = value is None or value is False

    if assign_type == 'is_user':
        conversation.transcript_segments[segment_idx].is_user = bool(value) if value is not None else False
        conversation.transcript_segments[segment_idx].person_id = None
    elif assign_type == 'person_id':
        conversation.transcript_segments[segment_idx].is_user = False
        conversation.transcript_segments[segment_idx].person_id = value
    else:
        print(assign_type)
        raise HTTPException(status_code=400, detail="Invalid assign type")

    conversations_db.update_conversation_segments(
        uid, conversation_id, [segment.dict() for segment in conversation.transcript_segments]
    )
    # thinh's note: disabled for now
    # segment_words = len(conversation.transcript_segments[segment_idx].text.split(' '))
    # # TODO: can do this async
    # if use_for_speech_training and not is_unassigning and segment_words > 5:  # some decent sample at least
    #     person_id = value if assign_type == 'person_id' else None
    #     expand_speech_profile(conversation_id, uid, segment_idx, assign_type, person_id)
    # else:
    #     path = f'{conversation_id}_segment_{segment_idx}.wav'
    #     delete_additional_profile_audio(uid, path)
    #     delete_speech_sample_for_people(uid, path)

    return conversation


@router.patch(
    '/v1/conversations/{conversation_id}/assign-speaker/{speaker_id}',
    response_model=Conversation,
    tags=['conversations'],
)
def set_assignee_conversation_segment(
    conversation_id: str,
    speaker_id: int,
    assign_type: str,
    value: Optional[str] = None,
    use_for_speech_training: bool = True,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Another complex endpoint.

    Modify the assignee of all segments in the transcript of a conversation with the given speaker_id.
    But,
    if `use_for_speech_training` is True, the corresponding audio segment will be used for speech training.

    Speech training of whom?

    If `assign_type` is 'is_user', the segment will be used for the user speech training.
    If `assign_type` is 'person_id', the segment will be used for the person with the given id speech training.

    What is required for a segment to be used for speech training?
    1. The segment must have more than 5 words.
    2. The conversation audio file should be already stored in the user's bucket.

    :return: The updated conversation.
    """
    print(
        'set_assignee_conversation_segment',
        conversation_id,
        speaker_id,
        assign_type,
        value,
        use_for_speech_training,
        uid,
    )
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)

    if value == 'null':
        value = None

    is_unassigning = value is None or value is False

    if assign_type == 'is_user':
        for segment in conversation.transcript_segments:
            if segment.speaker_id == speaker_id:
                segment.is_user = bool(value) if value is not None else False
                segment.person_id = None
    elif assign_type == 'person_id':
        for segment in conversation.transcript_segments:
            if segment.speaker_id == speaker_id:
                print(segment.speaker_id, speaker_id, value)
                segment.is_user = False
                segment.person_id = value
    else:
        print(assign_type)
        raise HTTPException(status_code=400, detail="Invalid assign type")

    conversations_db.update_conversation_segments(
        uid, conversation_id, [segment.dict() for segment in conversation.transcript_segments]
    )
    # This will be used when we setup recording for conversations, not used for now
    # get the segment with the most words with the speaker_id
    # segment_idx = 0
    # segment_words = 0
    # for segment in conversation.transcript_segments:
    #     if segment.speaker == speaker_id:
    #         if len(segment.text.split(' ')) > segment_words:
    #             segment_words = len(segment.text.split(' '))
    #             if segment_words > 5:
    #                 segment_idx = segment.idx
    #
    # if use_for_speech_training and not is_unassigning and segment_words > 5:  # some decent sample at least
    #     person_id = value if assign_type == 'person_id' else None
    #     expand_speech_profile(conversation_id, uid, segment_idx, assign_type, person_id)
    # else:
    #     path = f'{conversation_id}_segment_{segment_idx}.wav'
    #     delete_additional_profile_audio(uid, path)
    #     delete_speech_sample_for_people(uid, path)

    return conversation


@router.patch(
    '/v1/conversations/{conversation_id}/segments/assign-bulk',
    response_model=Conversation,
    tags=['conversations'],
)
def assign_segments_bulk(
    conversation_id: str,
    data: BulkAssignSegmentsRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)

    value = data.value
    if value == 'null':
        value = None

    segment_map = {segment.id: segment for segment in conversation.transcript_segments}

    for segment_id in data.segment_ids:
        if segment_id in segment_map:
            segment = segment_map[segment_id]
            if data.assign_type == 'is_user':
                segment.is_user = bool(value) if value is not None else False
                segment.person_id = None
            elif data.assign_type == 'person_id':
                segment.is_user = False
                segment.person_id = value
            else:
                raise HTTPException(status_code=400, detail="Invalid assign type")

    conversations_db.update_conversation_segments(
        uid, conversation_id, [segment.dict() for segment in conversation.transcript_segments]
    )
    return conversation


# *********************************************
# *********** SHARING conversations ***********
# *********************************************


@router.patch('/v1/conversations/{conversation_id}/visibility', tags=['conversations'])
def set_conversation_visibility(
    conversation_id: str, value: ConversationVisibility, uid: str = Depends(auth.get_current_user_uid)
):
    print('update_conversation_visibility', conversation_id, value, uid)
    _get_valid_conversation_by_id(uid, conversation_id)
    conversations_db.set_conversation_visibility(uid, conversation_id, value)
    if value == ConversationVisibility.private:
        redis_db.remove_conversation_to_uid(conversation_id)
        redis_db.remove_public_conversation(conversation_id)
    else:
        redis_db.store_conversation_to_uid(conversation_id, uid)
        redis_db.add_public_conversation(conversation_id)

    return {"status": "Ok"}


@router.patch('/v1/conversations/{conversation_id}/starred', tags=['conversations'])
def set_conversation_starred(conversation_id: str, starred: bool, uid: str = Depends(auth.get_current_user_uid)):
    print('update_conversation_starred', conversation_id, starred, uid)
    _get_valid_conversation_by_id(uid, conversation_id)
    conversations_db.set_conversation_starred(uid, conversation_id, starred)
    return {"status": "Ok"}


@router.get("/v1/conversations/{conversation_id}/shared", tags=['conversations'])
def get_shared_conversation_by_id(conversation_id: str):
    uid = redis_db.get_conversation_uid(conversation_id)
    if not uid:
        raise HTTPException(status_code=404, detail="Conversation is private")

    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    visibility = conversation.get('visibility', ConversationVisibility.private)
    if not visibility or visibility == ConversationVisibility.private:
        raise HTTPException(status_code=404, detail="Conversation is private")
    conversation = Conversation(**conversation)
    conversation.geolocation = None

    # Fetch people data for speaker names
    person_ids = conversation.get_person_ids()
    people = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, person_ids)
        people = [Person(**p) for p in people_data]

    # Return conversation with people data
    response_dict = conversation.as_dict_cleaned_dates()
    response_dict['people'] = [p.dict() for p in people]
    return response_dict


@router.get("/v1/public-conversations", response_model=List[Conversation], tags=['conversations'])
def get_public_conversations(offset: int = 0, limit: int = 1000):
    conversations = redis_db.get_public_conversations()
    data = []

    conversation_uids = redis_db.get_conversation_uids(conversations)

    data = [[uid, conversation_id] for conversation_id, uid in conversation_uids.items() if uid]
    # TODO: sort in some way to have proper pagination

    conversations = conversations_db.get_public_conversations(data[offset : offset + limit])
    for conversation in conversations:
        conversation['geolocation'] = None
    return conversations


@router.post("/v1/conversations/search", response_model=dict, tags=['conversations'])
def search_conversations_endpoint(search_request: SearchRequest, uid: str = Depends(auth.get_current_user_uid)):
    # Convert ISO datetime strings to Unix timestamps if provided
    start_timestamp = None
    end_timestamp = None

    if search_request.start_date:
        start_timestamp = int(datetime.fromisoformat(search_request.start_date).timestamp())

    if search_request.end_date:
        end_timestamp = int(datetime.fromisoformat(search_request.end_date).timestamp())

    return search_conversations(
        query=search_request.query,
        page=search_request.page,
        per_page=search_request.per_page,
        uid=uid,
        include_discarded=search_request.include_discarded,
        start_date=start_timestamp,
        end_date=end_timestamp,
    )


@router.get("/v1/conversations/{conversation_id}/suggested-apps", response_model=dict, tags=['conversations'])
def get_conversation_suggested_apps(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    from utils.apps import get_available_apps, get_available_app_by_id_with_reviews
    from models.app import App

    conversation_data = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation_data)

    # Get suggested app models with full data (similar to /v1/apps endpoint)
    suggested_apps = []
    for app_id in conversation.suggested_summarization_apps:
        app_data = get_available_app_by_id_with_reviews(app_id, uid)
        if app_data:
            app = App(**app_data)
            # Add user-specific data
            from utils.apps import get_is_user_paid_app

            app.is_user_paid = get_is_user_paid_app(app.id, uid)

            # Add payment link with user reference
            if app.payment_link:
                app.payment_link = f'{app.payment_link}?client_reference_id=uid_{uid}'

            # Generate thumbnail URLs if thumbnails exist
            if app.thumbnails:
                from utils.other.storage import get_app_thumbnail_url

                app.thumbnail_urls = [get_app_thumbnail_url(thumbnail_id) for thumbnail_id in app.thumbnails]

            suggested_apps.append(app)

    return {"suggested_apps": [app.dict() for app in suggested_apps], "conversation_id": conversation_id}


@router.post("/v1/conversations/{conversation_id}/test-prompt", response_model=dict, tags=['conversations'])
def test_prompt(conversation_id: str, request: TestPromptRequest, uid: str = Depends(auth.get_current_user_uid)):
    conversation_data = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation_data)

    full_transcript = "\n".join([seg.text for seg in conversation.transcript_segments if seg.text])

    if not full_transcript:
        raise HTTPException(status_code=400, detail="Conversation has no text content to summarize.")

    summary = generate_summary_with_prompt(full_transcript, request.prompt)

    return {"summary": summary}


# *********************************************
# *********** MERGING conversations ***********
# *********************************************


@router.post('/v1/conversations/merge', response_model=MergeConversationsResponse, tags=['conversations'])
async def merge_conversations(
    request: MergeConversationsRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Merge multiple conversations into a new conversation (async).

    Flow:
    1. Validates conversations (locked? completed?)
    2. Returns immediately with 200 OK
    3. Background task creates new merged conversation
    4. Background task deletes source conversations
    5. FCM notification sent on completion

    The merged conversation will have:
    - A new ID (source conversations are deleted)
    - Merged transcript segments with adjusted timestamps
    - Copied audio chunks
    - Regenerated title, summary, action items, memories via process_conversation()
    """
    from utils.conversations.merge_conversations import validate_merge_compatibility, perform_merge_async

    # Validate minimum number of conversations
    if len(request.conversation_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 conversations required to merge")

    # Fetch all conversations
    conversations = []
    for conv_id in request.conversation_ids:
        conv = conversations_db.get_conversation(uid, conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail=f"Conversation {conv_id} not found")
        conversations.append(conv)

    # Validate merge compatibility (returns warning for large gaps but doesn't reject)
    is_valid, error_message, warning_message = validate_merge_compatibility(conversations)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    # Set all source conversations to 'merging' status so user knows they're being processed
    for conv_id in request.conversation_ids:
        conversations_db.update_conversation_status(uid, conv_id, ConversationStatus.merging)

    # Start background merge task
    background_tasks.add_task(
        perform_merge_async,
        uid=uid,
        conversation_ids=request.conversation_ids,
        reprocess=request.reprocess,
    )

    return MergeConversationsResponse(
        status="merging",
        message="Merge started",
        warning=warning_message,
        conversation_ids=request.conversation_ids,
    )
