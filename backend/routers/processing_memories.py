from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

import utils.processing_memories as processing_memory_utils
from models.processing_memory import UpdateProcessingMemoryResponse, UpdateProcessingMemory, BasicProcessingMemoryResponse, BasicProcessingMemoriesResponse, DetailProcessingMemoryResponse, DetailProcessingMemoriesResponse
from utils.other import endpoints as auth

router = APIRouter()


@router.patch("/v1/processing-memories/{processing_memory_id}", response_model=UpdateProcessingMemoryResponse,
              tags=['processing_memories'])
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

    updates_processing_memory.id = processing_memory_id
    processing_memory = processing_memory_utils.update_basic_processing_memory(uid, updates_processing_memory)
    if not processing_memory:
        raise HTTPException(status_code=404, detail="Processing memory not found")

    return UpdateProcessingMemoryResponse(result=processing_memory)

@router.get("/v1/processing-memories/{processing_memory_id}", response_model=DetailProcessingMemoryResponse,
            tags=['processing_memories'])
def get_processing_memory(
        processing_memory_id: str,
        uid: str = Depends(auth.get_current_user_uid)
):
    """
    Get ProcessingMemory endpoint.
    :param processing_memory_id:
    :param uid: user id.
    :return: The processing_memory.
    """

    update_processing_memory.id = processing_memory_id
    processing_memory = processing_memory_utils.get_processing_memory(uid, processing_memory_id)
    if not processing_memory:
        raise HTTPException(status_code=404, detail="Processing memory not found")

    return DetailProcessingMemoryResponse(result=processing_memory)

@router.get("/v1/processing-memories", response_model=DetailProcessingMemoriesResponse,
            tags=['processing_memories'])
def list_processing_memory(uid: str = Depends(auth.get_current_user_uid), filter_ids: Optional[str] = None):
    """
    List ProcessingMemory endpoint.
    :param uid: user id.
    :return: The list of processing_memories.
    """
    processing_memories = processing_memory_utils.get_processing_memories(uid, filter_ids=filter_ids.split(",") if filter_ids else [], limit=5)
    if not processing_memories or len(processing_memories) == 0:
        return DetailProcessingMemoriesResponse(result=[])

    return DetailProcessingMemoriesResponse(result=list(processing_memories))
