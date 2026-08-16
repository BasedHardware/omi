from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class TaskActionProvider(str, Enum):
    HUME = 'hume'


class TaskAction(str, Enum):
    HUME_MERSURE_USER_EXPRESSION = 'hume_mersure_user_expression'


class TaskStatus(str, Enum):
    PROCESSING = 'processing'
    DONE = 'done'
    ERROR = 'error'


class Task(BaseModel):
    id: str
    action: TaskAction
    status: TaskStatus
    created_at: datetime
    # Default to None (not yet executed). A bare datetime.now() default is evaluated once at class
    # definition, so every Task built without an explicit executed_at would share the process-start
    # timestamp and look already-executed. updated_at below already uses the correct None default.
    executed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    request_id: Optional[str] = None
    memory_id: Optional[str] = None
    user_uid: Optional[str] = None
