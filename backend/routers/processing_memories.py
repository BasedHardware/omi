from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

import utils.processing_memories as processing_memory_utils
from models.processing_memory import DetailProcessingMemoryResponse, \
    DetailProcessingMemoriesResponse, UpdateProcessingMemory, UpdateProcessingMemoryResponse, BasicProcessingMemory
from database.redis_db import cache_user_geolocation
from utils.other import endpoints as auth

v1_router = APIRouter(prefix="/v1", tags=['processing_memories'])

@v1_router.patch(
        "/processing-memories/{processing_memory_id}",
        response_model=UpdateProcessingMemoryResponse,
        deprecated=True
)
def update_processing_memory(
        processing_memory_id: str,
        updates_processing_memory: UpdateProcessingMemory,
        uid: str = Depends(auth.get_current_user_uid)
):
    """
    Update ProcessingMemory endpoint.
    :param processing_memory_id:
    :param updates_processing_memory: data to update processing_memory
    :param uid: user id.
    :return: The new processing_memory updated.
    """

    print(f"Update processing memory {processing_memory_id}")

    # Keep up-to-date with the new logic
    geolocation = updates_processing_memory.geolocation
    if geolocation:
        cache_user_geolocation(uid, geolocation.dict())

    processing_memory = processing_memory_utils.get_processing_memory(uid, processing_memory_id)
    if not processing_memory:
        raise HTTPException(status_code=404, detail="Processing memory not found")

    return UpdateProcessingMemoryResponse(result=BasicProcessingMemory(**processing_memory.dict()))


@v1_router.get(
    "/processing-memories/{processing_memory_id}",
    response_model=DetailProcessingMemoryResponse,
)
def get_processing_memory(processing_memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Get ProcessingMemory endpoint.
    :param processing_memory_id:
    :param uid: user id.
    :return: The processing_memory.
    """

    # update_processing_memory.id = processing_memory_id
    processing_memory = processing_memory_utils.get_processing_memory(uid, processing_memory_id)
    if not processing_memory:
        raise HTTPException(status_code=404, detail="Processing memory not found")

    return DetailProcessingMemoryResponse(result=processing_memory)


@v1_router.get(
        "/processing-memories",
        response_model=DetailProcessingMemoriesResponse,
)
def list_processing_memory(uid: str = Depends(auth.get_current_user_uid), filter_ids: Optional[str] = None):
    """
    List ProcessingMemory endpoint.
    :param filter_ids: filter by processing_memory ids.
    :param uid: user id.
    :return: The list of processing_memories.
    """
    processing_memories = processing_memory_utils.get_processing_memories(
        uid, filter_ids=filter_ids.split(",") if filter_ids else [], limit=5
    )
    if not processing_memories or len(processing_memories) == 0:
        return DetailProcessingMemoriesResponse(result=[])

    return DetailProcessingMemoriesResponse(result=list(processing_memories))
