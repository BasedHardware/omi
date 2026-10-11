"""User-profile tool handler for the hosted MCP server."""

from typing import Any, Dict, Optional

import database.users as users_db
from utils.memory.product_authorization import ProductAuthorizationContext


def get_user_profile(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    profile = users_db.get_ai_user_profile(uid)
    if not profile or not profile.get("profile_text"):
        return {"profile": None, "message": "No profile has been generated for this user yet."}
    return {
        "profile_text": profile.get("profile_text"),
        "generated_at": profile.get("generated_at"),
        "data_sources_used": profile.get("data_sources_used"),
    }
