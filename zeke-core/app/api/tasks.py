from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..services.task_service import TaskService
from ..models.task import TaskResponse, TaskUpdate, TaskPriority, TaskStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    due_at: Optional[str] = None
    tags: List[str] = []


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_at: Optional[datetime] = None


def get_task_service() -> TaskService:
    return TaskService()


@router.post("/", response_model=TaskResponse)
async def create_task(
    request: TaskCreateRequest,
    service: TaskService = Depends(get_task_service)
):
    task = await service.create(
        user_id="default_user",
        title=request.title,
        description=request.description,
        priority=request.priority,
        due_at=request.due_at,
        tags=request.tags
    )
    return task


@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    status: str = Query("pending", enum=["pending", "completed", "all"]),
    limit: int = Query(20, le=100),
    service: TaskService = Depends(get_task_service)
):
    return await service.list(
        user_id="default_user",
        status=status,
        limit=limit
    )


@router.get("/due-soon", response_model=List[TaskResponse])
async def get_due_soon(
    hours: int = Query(24, le=168),
    service: TaskService = Depends(get_task_service)
):
    return await service.get_due_soon(
        user_id="default_user",
        hours=hours
    )


@router.get("/overdue", response_model=List[TaskResponse])
async def get_overdue(
    service: TaskService = Depends(get_task_service)
):
    return await service.get_overdue(user_id="default_user")


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    service: TaskService = Depends(get_task_service)
):
    task = await service.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    request: TaskUpdateRequest,
    service: TaskService = Depends(get_task_service)
):
    update_data = TaskUpdate(
        title=request.title,
        description=request.description,
        priority=TaskPriority(request.priority) if request.priority else None,
        status=TaskStatus(request.status) if request.status else None,
        due_at=request.due_at
    )
    
    task = await service.update(task_id, update_data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: str,
    service: TaskService = Depends(get_task_service)
):
    task = await service.complete(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    service: TaskService = Depends(get_task_service)
):
    success = await service.delete(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}
