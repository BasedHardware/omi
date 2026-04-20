"""SharePoint + OneDrive file operations via Microsoft Graph."""
from __future__ import annotations

from typing import Any

from services.graph_client import GraphClient


def _slim_item(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": it.get("id"),
        "name": it.get("name"),
        "size": it.get("size"),
        "modified": it.get("lastModifiedDateTime"),
        "web_url": it.get("webUrl"),
        "folder": "folder" in it,
        "mime": (it.get("file") or {}).get("mimeType"),
    }


async def list_recent_files(user_id: str, limit: int = 15) -> list[dict[str, Any]]:
    async with GraphClient(user_id) as g:
        data = await g.get("/me/drive/recent", params={"$top": limit})
        return [_slim_item(i) for i in data.get("value", [])]


async def search_files(user_id: str, query: str, limit: int = 15) -> list[dict[str, Any]]:
    async with GraphClient(user_id) as g:
        data = await g.get(
            f"/me/drive/root/search(q='{query}')",
            params={"$top": limit},
        )
        return [_slim_item(i) for i in data.get("value", [])]


async def upload_text_file(
    user_id: str,
    folder_path: str,
    filename: str,
    content: str,
) -> dict[str, Any]:
    """Simple upload via Graph PUT (for files <4MB).

    folder_path: e.g. "Documents/OMI-Notes" (relative to OneDrive root).
    """
    folder_path = folder_path.strip("/")
    path = f"/me/drive/root:/{folder_path}/{filename}:/content"
    async with GraphClient(user_id) as g:
        data = await g.put_bytes(path, content.encode("utf-8"), content_type="text/plain")
        return _slim_item(data) if data else {"status": "uploaded", "name": filename}


async def read_file_text(user_id: str, item_id: str) -> dict[str, Any]:
    async with GraphClient(user_id) as g:
        meta = await g.get(f"/me/drive/items/{item_id}")
        # Download content via /content endpoint
        import httpx
        from services.auth import get_access_token

        token = await get_access_token(user_id)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/content",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            try:
                text = resp.content.decode("utf-8")
            except UnicodeDecodeError:
                text = f"<binary {len(resp.content)} bytes>"
        return {**_slim_item(meta), "content": text}
