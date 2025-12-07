from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel

from ..services.curation_service import MemoryCurationService
from ..models.memory import MemoryResponse, CurationRunResponse

router = APIRouter(prefix="/curation", tags=["curation"])

curation_service = MemoryCurationService()


class CurationRunRequest(BaseModel):
    user_id: str = "default_user"
    batch_size: int = 20
    auto_delete: bool = False
    reprocess_all: bool = False


class MemoryActionRequest(BaseModel):
    memory_id: str
    action: str
    delete_permanently: bool = False


@router.get("/stats/{user_id}")
async def get_curation_stats(user_id: str):
    try:
        stats = await curation_service.get_curation_stats(user_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/flagged/{user_id}", response_model=List[MemoryResponse])
async def get_flagged_memories(user_id: str, limit: int = 50):
    try:
        memories = await curation_service.get_flagged_memories(user_id, limit)
        return memories
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CurationQueuedResponse(BaseModel):
    status: str = "queued"
    message: str = "Curation job dispatched to background worker"


@router.post("/run")
async def trigger_curation_run(request: CurationRunRequest, async_mode: bool = True):
    try:
        if async_mode:
            from ..core.tasks import run_memory_curation
            run_memory_curation.delay(request.user_id)
            return CurationQueuedResponse()
        
        result = await curation_service.run_curation(
            user_id=request.user_id,
            batch_size=request.batch_size,
            auto_delete=request.auto_delete,
            reprocess_all=request.reprocess_all
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve/{memory_id}", response_model=MemoryResponse)
async def approve_memory(memory_id: str):
    try:
        memory = await curation_service.approve_memory(memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        return memory
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reject/{memory_id}")
async def reject_memory(memory_id: str, delete_permanently: bool = False):
    try:
        success = await curation_service.reject_memory(memory_id, delete=delete_permanently)
        if not success:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"status": "success", "deleted": delete_permanently}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-action")
async def batch_action(actions: List[MemoryActionRequest]):
    results = []
    for action_req in actions:
        try:
            if action_req.action == "approve":
                memory = await curation_service.approve_memory(action_req.memory_id)
                results.append({
                    "memory_id": action_req.memory_id,
                    "status": "success" if memory else "not_found"
                })
            elif action_req.action == "reject":
                success = await curation_service.reject_memory(
                    action_req.memory_id,
                    delete=action_req.delete_permanently
                )
                results.append({
                    "memory_id": action_req.memory_id,
                    "status": "success" if success else "not_found"
                })
            else:
                results.append({
                    "memory_id": action_req.memory_id,
                    "status": "error",
                    "message": f"Unknown action: {action_req.action}"
                })
        except Exception as e:
            results.append({
                "memory_id": action_req.memory_id,
                "status": "error",
                "message": str(e)
            })
    
    return {"results": results}
