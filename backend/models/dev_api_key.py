from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DevApiKey(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None


class DevApiKeyDB(DevApiKey):
    user_id: str
    hashed_key: str


class DevApiKeyCreate(BaseModel):
    name: str


class DevApiKeyCreated(DevApiKey):
    key: str
