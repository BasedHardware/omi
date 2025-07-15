from fastapi import APIRouter, Depends, HTTPException

import database.conversations as conversations_db
import database.redis_db as redis_db
from database.vector_db import delete_vector
from models.conversation import *
from models.conversation import SearchRequest

from utils.conversations.process_conversation import process_conversation, retrieve_in_progress_conversation
from utils.conversations.search import search_conversations
from utils.llm.conversation_processing import generate_summary_with_prompt
from utils.other import endpoints as auth
from utils.other.storage import get_conversation_recording_if_exists
from utils.app_integrations import trigger_external_integrations

router = APIRouter()


def _get_conversation_by_id(uid: str, conversation_id: str) -> dict:
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("/v1/conversations", response_model=CreateConversationResponse, tags=['conversations'])
def process_in_progress_conversation(uid: str = Depends(auth.get_current_user_uid)):
    conversation = retrieve_in_progress_conversation(uid)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation in progress not found")
    redis_db.remove_in_progress_conversation_id(uid)

    conversation = Conversation(**conversation)
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
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation = Conversation(**conversation)
    if not language_code:
        language_code = conversation.language or 'en'

    return process_conversation(uid, language_code, conversation, force_process=True, is_reprocess=True, app_id=app_id)


@router.get('/v1/conversations', response_model=List[Conversation], tags=['conversations'])
def get_conversations(
    limit: int = 100,
    offset: int = 0,
    statuses: Optional[str] = "processing,completed",
    include_discarded: bool = True,
    uid: str = Depends(auth.get_current_user_uid),
):
    print('get_conversations', uid, limit, offset, statuses)
    # force convos statuses to processing, completed on the empty filter
    if len(statuses) == 0:
        statuses = "processing,completed"
    return conversations_db.get_conversations(
        uid,
        limit,
        offset,
        include_discarded=include_discarded,
        statuses=statuses.split(",") if len(statuses) > 0 else [],
    )


@router.get("/v1/conversations/{conversation_id}", response_model=Conversation, tags=['conversations'])
def get_conversation_by_id(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    print('get_conversation_by_id', uid, conversation_id)
    return _get_conversation_by_id(uid, conversation_id)


@router.patch("/v1/conversations/{conversation_id}/title", tags=['conversations'])
def patch_conversation_title(conversation_id: str, title: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_conversation_by_id(uid, conversation_id)
    conversations_db.update_conversation_title(uid, conversation_id, title)
    return {'status': 'Ok'}


@router.get(
    "/v1/conversations/{conversation_id}/photos", response_model=List[ConversationPhoto], tags=['conversations']
)
def get_conversation_photos(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_conversation_by_id(uid, conversation_id)
    return conversations_db.get_conversation_photos(uid, conversation_id)


@router.get(
    "/v1/conversations/{conversation_id}/transcripts",
    response_model=Dict[str, List[TranscriptSegment]],
    tags=['conversations'],
)
def get_conversation_transcripts_by_models(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_conversation_by_id(uid, conversation_id)
    return conversations_db.get_conversation_transcripts_by_model(uid, conversation_id)


@router.delete("/v1/conversations/{conversation_id}", status_code=204, tags=['conversations'])
def delete_conversation(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    print('delete_conversation', conversation_id, uid)
    conversations_db.delete_conversation(uid, conversation_id)
    delete_vector(conversation_id)
    return {"status": "Ok"}


@router.get("/v1/conversations/{conversation_id}/recording", response_model=dict, tags=['conversations'])
def conversation_has_audio_recording(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_conversation_by_id(uid, conversation_id)
    return {'has_recording': get_conversation_recording_if_exists(uid, conversation_id) is not None}


@router.patch("/v1/conversations/{conversation_id}/events", response_model=dict, tags=['conversations'])
def set_conversation_events_state(
    conversation_id: str, data: SetConversationEventsStateRequest, uid: str = Depends(auth.get_current_user_uid)
):
    conversation = _get_conversation_by_id(uid, conversation_id)
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
    conversation = _get_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)
    action_items = conversation.structured.action_items
    for i, action_item_idx in enumerate(data.items_idx):
        if action_item_idx >= len(action_items):
            continue
        action_items[action_item_idx].completed = data.values[i]

    conversations_db.update_conversation_action_items(
        uid, conversation_id, [action_item.dict() for action_item in action_items]
    )
    return {"status": "Ok"}


@router.patch(
    "/v1/conversations/{conversation_id}/action-items/{action_item_idx}", response_model=dict, tags=['conversations']
)
def update_action_item_description(
    conversation_id: str, data: UpdateActionItemDescriptionRequest, uid=Depends(auth.get_current_user_uid)
):
    conversation = _get_conversation_by_id(uid, conversation_id)
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
    return {"status": "Ok"}


@router.delete("/v1/conversations/{conversation_id}/action-items", response_model=dict, tags=['conversations'])
def delete_action_item(data: DeleteActionItemRequest, conversation_id: str, uid=Depends(auth.get_current_user_uid)):
    conversation = _get_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation)
    action_items = conversation.structured.action_items
    updated_action_items = [item for item in action_items if not (item.description == data.description)]
    conversations_db.update_conversation_action_items(
        uid, conversation_id, [action_item.dict() for action_item in updated_action_items]
    )
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
    conversation = _get_conversation_by_id(uid, conversation_id)
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
    conversation = _get_conversation_by_id(uid, conversation_id)
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


# *********************************************
# *********** SHARING conversations ***********
# *********************************************


@router.patch('/v1/conversations/{conversation_id}/visibility', tags=['conversations'])
def set_conversation_visibility(
    conversation_id: str, value: ConversationVisibility, uid: str = Depends(auth.get_current_user_uid)
):
    print('update_conversation_visibility', conversation_id, value, uid)
    _get_conversation_by_id(uid, conversation_id)
    conversations_db.set_conversation_visibility(uid, conversation_id, value)
    if value == ConversationVisibility.private:
        redis_db.remove_conversation_to_uid(conversation_id)
        redis_db.remove_public_conversation(conversation_id)
    else:
        redis_db.store_conversation_to_uid(conversation_id, uid)
        redis_db.add_public_conversation(conversation_id)

    return {"status": "Ok"}


@router.get("/v1/conversations/{conversation_id}/shared", response_model=Conversation, tags=['conversations'])
def get_shared_conversation_by_id(conversation_id: str):
    uid = redis_db.get_conversation_uid(conversation_id)
    if not uid:
        raise HTTPException(status_code=404, detail="Conversation is private")

    # TODO: include speakers and people matched?
    # TODO: other fields that  shouldn't be included?
    conversation = _get_conversation_by_id(uid, conversation_id)
    visibility = conversation.get('visibility', ConversationVisibility.private)
    if not visibility or visibility == ConversationVisibility.private:
        raise HTTPException(status_code=404, detail="Conversation is private")
    conversation = Conversation(**conversation)
    conversation.geolocation = None
    return conversation


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


@router.post("/v1/conversations/{conversation_id}/test-prompt", response_model=dict, tags=['conversations'])
def test_prompt(conversation_id: str, request: TestPromptRequest, uid: str = Depends(auth.get_current_user_uid)):
    conversation_data = _get_conversation_by_id(uid, conversation_id)
    conversation = Conversation(**conversation_data)

    full_transcript = "\n".join([seg.text for seg in conversation.transcript_segments if seg.text])

    if not full_transcript:
        raise HTTPException(status_code=400, detail="Conversation has no text content to summarize.")

    summary = generate_summary_with_prompt(full_transcript, request.prompt)

    return {"summary": summary}
