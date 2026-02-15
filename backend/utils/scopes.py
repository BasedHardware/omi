from typing import List, Optional


# Available scopes
class Scopes:
    CONVERSATIONS_READ = "conversations:read"
    CONVERSATIONS_WRITE = "conversations:write"
    MEMORIES_READ = "memories:read"
    MEMORIES_WRITE = "memories:write"
    ACTION_ITEMS_READ = "action_items:read"
    ACTION_ITEMS_WRITE = "action_items:write"
    GOALS_READ = "goals:read"
    GOALS_WRITE = "goals:write"


AVAILABLE_SCOPES = [
    Scopes.CONVERSATIONS_READ,
    Scopes.CONVERSATIONS_WRITE,
    Scopes.MEMORIES_READ,
    Scopes.MEMORIES_WRITE,
    Scopes.ACTION_ITEMS_READ,
    Scopes.ACTION_ITEMS_WRITE,
    Scopes.GOALS_READ,
    Scopes.GOALS_WRITE,
]

# Default scopes: read-only access
READ_ONLY_SCOPES = [
    Scopes.CONVERSATIONS_READ,
    Scopes.MEMORIES_READ,
    Scopes.ACTION_ITEMS_READ,
    Scopes.GOALS_READ,
]


def validate_scopes(scopes: List[str]) -> bool:
    """Validate that all scopes are valid"""
    return all(scope in AVAILABLE_SCOPES for scope in scopes)


def has_scope(user_scopes: Optional[List[str]], required_scope: str) -> bool:
    """Check if user has required scope. None scopes are treated as read-only."""
    if user_scopes is None:
        # If scopes don't exist, treat as read-only
        return required_scope in READ_ONLY_SCOPES
    return required_scope in user_scopes
