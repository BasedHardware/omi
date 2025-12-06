from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

from ..services.memory_service import MemoryService
from ..models.memory import MemoryResponse, MemoryCategory

router = APIRouter(prefix="/memories", tags=["memories"])


class MemoryCreateRequest(BaseModel):
    content: str
    category: str = "manual"
    tags: List[str] = []


class MemorySearchRequest(BaseModel):
    query: str
    limit: int = 10


class MemorySearchResponse(BaseModel):
    memories: List[str]


def get_memory_service() -> MemoryService:
    return MemoryService()


@router.post("/", response_model=MemoryResponse)
async def create_memory(
    request: MemoryCreateRequest,
    service: MemoryService = Depends(get_memory_service)
):
    memory = await service.create(
        user_id="default_user",
        content=request.content,
        category=request.category,
        manually_added=True
    )
    return memory


@router.get("/", response_model=List[MemoryResponse])
async def list_memories(
    limit: int = Query(20, le=100),
    category: Optional[str] = None,
    service: MemoryService = Depends(get_memory_service)
):
    return await service.get_recent(
        user_id="default_user",
        limit=limit,
        category=category
    )


@router.post("/search", response_model=MemorySearchResponse)
async def search_memories(
    request: MemorySearchRequest,
    service: MemoryService = Depends(get_memory_service)
):
    results = await service.search(
        user_id="default_user",
        query=request.query,
        limit=request.limit
    )
    return MemorySearchResponse(memories=results)


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service)
):
    memory = await service.get_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service)
):
    success = await service.delete(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}
