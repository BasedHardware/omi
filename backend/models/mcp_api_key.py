from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

MCP_SCOPES_SUPPORTED = [
    "memories.read",
    "memories.write",
    "conversations.read",
    "action_items.read",
    "goals.read",
    "chat.read",
    "screen_activity.read",
    "people.read",
    "people.write",
]
MCP_DEFAULT_API_KEY_SCOPES = list(MCP_SCOPES_SUPPORTED)
MCP_LEGACY_API_KEY_SCOPES = [scope for scope in MCP_SCOPES_SUPPORTED if scope.endswith(".read")] + ["memories.write"]


class McpApiKey(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    scopes: Optional[List[str]] = None


class McpApiKeyDB(McpApiKey):
    user_id: str
    hashed_key: str


class McpApiKeyCreate(BaseModel):
    name: str
    scopes: Optional[List[str]] = None


class McpApiKeyCreated(McpApiKey):
    key: str
