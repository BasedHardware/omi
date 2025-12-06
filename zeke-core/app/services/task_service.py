from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
import logging

from ..models.task import TaskDB, TaskCreate, TaskUpdate, TaskResponse, TaskStatus, TaskPriority
from ..core.database import get_db_context
from ..core.events import event_bus, Event, EventTypes

logger = logging.getLogger(__name__)


class TaskService:
    async def create(
        self,
        user_id: str,
        title: str,
        description: Optional[str] = None,
        due_at: Optional[str] = None,
        priority: str = "medium",
        conversation_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> TaskResponse:
        parsed_due = None
        if due_at:
            try:
                parsed_due = datetime.fromisoformat(due_at)
            except ValueError:
                pass
        
        with get_db_context() as db:
            task = TaskDB(
                uid=user_id,
                title=title,
                description=description,
                priority=priority,
                due_at=parsed_due,
                conversation_id=conversation_id,
                tags=tags or []
            )
            db.add(task)
            db.flush()
            db.refresh(task)
            
            result = TaskResponse.model_validate(task)
        
        event_bus.publish(Event(
            type=EventTypes.TASK_CREATED,
            data={"task_id": result.id, "user_id": user_id, "title": title}
        ))
        
        return result
    
    async def list(
        self,
        user_id: str,
        status: str = "pending",
        limit: int = 20
    ) -> List[TaskResponse]:
        with get_db_context() as db:
            query = db.query(TaskDB).filter(TaskDB.uid == user_id)
            
            if status != "all":
                query = query.filter(TaskDB.status == status)
            
            tasks = query.order_by(
                desc(TaskDB.due_at.is_(None)),
                TaskDB.due_at,
                desc(TaskDB.created_at)
            ).limit(limit).all()
            
            return [TaskResponse.model_validate(t) for t in tasks]
    
    async def get_by_id(self, task_id: str) -> Optional[TaskResponse]:
        with get_db_context() as db:
            task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
            if task:
                return TaskResponse.model_validate(task)
            return None
    
    async def update(
        self,
        task_id: str,
        data: TaskUpdate
    ) -> Optional[TaskResponse]:
        with get_db_context() as db:
            task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
            if not task:
                return None
            
            if data.title is not None:
                task.title = data.title
            if data.description is not None:
                task.description = data.description
            if data.priority is not None:
                task.priority = data.priority.value
            if data.status is not None:
                task.status = data.status.value
                if data.status == TaskStatus.completed:
                    task.completed_at = datetime.utcnow()
            if data.due_at is not None:
                task.due_at = data.due_at
            
            task.updated_at = datetime.utcnow()
            db.flush()
            db.refresh(task)
            
            return TaskResponse.model_validate(task)
    
    async def complete(self, task_id: str) -> Optional[TaskResponse]:
        with get_db_context() as db:
            task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
            if not task:
                return None
            
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            
            db.flush()
            db.refresh(task)
            
            result = TaskResponse.model_validate(task)
        
        event_bus.publish(Event(
            type=EventTypes.TASK_COMPLETED,
            data={"task_id": task_id}
        ))
        
        return result
    
    async def delete(self, task_id: str) -> bool:
        with get_db_context() as db:
            result = db.query(TaskDB).filter(TaskDB.id == task_id).delete()
            return result > 0
    
    async def get_due_soon(
        self,
        user_id: str,
        hours: int = 24
    ) -> List[TaskResponse]:
        with get_db_context() as db:
            cutoff = datetime.utcnow()
            end = datetime.utcnow().replace(hour=23, minute=59, second=59)
            
            tasks = db.query(TaskDB).filter(
                and_(
                    TaskDB.uid == user_id,
                    TaskDB.status == "pending",
                    TaskDB.due_at.isnot(None),
                    TaskDB.due_at <= end
                )
            ).order_by(TaskDB.due_at).all()
            
            return [TaskResponse.model_validate(t) for t in tasks]
    
    async def get_overdue(self, user_id: str) -> List[TaskResponse]:
        with get_db_context() as db:
            now = datetime.utcnow()
            
            tasks = db.query(TaskDB).filter(
                and_(
                    TaskDB.uid == user_id,
                    TaskDB.status == "pending",
                    TaskDB.due_at.isnot(None),
                    TaskDB.due_at < now
                )
            ).order_by(TaskDB.due_at).all()
            
            return [TaskResponse.model_validate(t) for t in tasks]
