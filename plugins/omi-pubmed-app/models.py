from typing import Optional
from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None
