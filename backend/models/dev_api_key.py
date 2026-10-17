from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class DevApiKey(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    scopes: Optional[List[str]] = None


class DevApiKeyDB(DevApiKey):
    user_id: str
    hashed_key: str


class DevApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: Optional[List[str]] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Key name cannot be empty')
        return v


class DevApiKeyCreated(DevApiKey):
    key: str
