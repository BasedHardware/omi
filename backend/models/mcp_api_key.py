from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class McpApiKey(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None


class McpApiKeyDB(McpApiKey):
    user_id: str
    hashed_key: str


class McpApiKeyCreate(BaseModel):
    name: str


class McpApiKeyCreated(McpApiKey):
    key: str
