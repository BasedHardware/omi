from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class McpApiKey(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    app_id: Optional[str] = None
    scopes: Optional[list[str]] = None


class McpApiKeyDB(McpApiKey):
    user_id: str
    hashed_key: str


class McpApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: Optional[list[str]] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Key name cannot be empty')
        return v


class McpApiKeyCreated(McpApiKey):
    key: str
