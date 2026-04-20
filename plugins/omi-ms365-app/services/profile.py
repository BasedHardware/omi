"""User profile helper."""
from __future__ import annotations

from typing import Any

from services.graph_client import GraphClient


async def me(user_id: str) -> dict[str, Any]:
    async with GraphClient(user_id) as g:
        data = await g.get("/me")
        return {
            "id": data.get("id"),
            "display_name": data.get("displayName"),
            "mail": data.get("mail") or data.get("userPrincipalName"),
            "job_title": data.get("jobTitle"),
            "preferred_language": data.get("preferredLanguage"),
        }
