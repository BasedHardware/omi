# DEPRECATED: This file has been deprecated long ago
#
# This file is deprecated and should be removed. The code is not used anymore and is not referenced in any other file.

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

import utils.processing_conversations as processing_conversation_utils
from models.processing_conversation import DetailProcessingConversationResponse, \
    DetailProcessingConversationsResponse, UpdateProcessingConversation, UpdateProcessingConversationResponse, \
    BasicProcessingConversation
from database.redis_db import cache_user_geolocation
from utils.other import endpoints as auth

router = APIRouter()


# Deprecated
@router.patch("/v1/processing-memories/{processing_conversation_id}",
              response_model=UpdateProcessingConversationResponse,
              tags=['processing_memories'])
def update_processing_conversation(
        processing_conversation_id: str,
        updates_processing_conversation: UpdateProcessingConversation,
        uid: str = Depends(auth.get_current_user_uid)
):
    """
    Update ProcessingMemory endpoint.
    :param processing_conversation_id:
    :param updates_processing_conversation: data to update processing_memory
    :param uid: user id.
    :return: The new processing_memory updated.
    """

    print(f"Update processing conversation {processing_conversation_id}")

    # Keep up-to-date with the new logic
    geolocation = updates_processing_conversation.geolocation
    if geolocation:
        cache_user_geolocation(uid, geolocation.dict())

    processing_conversation = processing_conversation_utils.get_processing_conversation(uid, processing_conversation_id)
    if not processing_conversation:
        raise HTTPException(status_code=404, detail="Processing conversation not found")

    return UpdateProcessingConversationResponse(result=BasicProcessingConversation(**processing_conversation.dict()))


@router.get(
    "/v1/processing-memories/{processing_conversation_id}",
    response_model=DetailProcessingConversationResponse,
    tags=['processing_memories']
)
def get_processing_conversation(processing_conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Get ProcessingMemory endpoint.
    :param processing_conversation_id:
    :param uid: user id.
    :return: The processing_memory.
    """

    # update_processing_memory.id = processing_memory_id
    processing_conversation = processing_conversation_utils.get_processing_conversation(uid, processing_conversation_id)
    if not processing_conversation:
        raise HTTPException(status_code=404, detail="Processing conversation not found")

    return DetailProcessingConversationResponse(result=processing_conversation)


@router.get("/v1/processing-memories", response_model=DetailProcessingConversationsResponse,
            tags=['processing_memories'])
def list_processing_conversation(uid: str = Depends(auth.get_current_user_uid), filter_ids: Optional[str] = None):
    """
    List ProcessingMemory endpoint.
    :param filter_ids: filter by processing_memory ids.
    :param uid: user id.
    :return: The list of processing_memories.
    """
    processing_memories = processing_conversation_utils.get_processing_memories(
        uid, filter_ids=filter_ids.split(",") if filter_ids else [], limit=5
    )
    if not processing_memories or len(processing_memories) == 0:
        return DetailProcessingConversationsResponse(result=[])

    return DetailProcessingConversationsResponse(result=list(processing_memories))
