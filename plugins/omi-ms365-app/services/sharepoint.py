"""SharePoint + OneDrive file operations via Microsoft Graph."""
from __future__ import annotations

from typing import Any

from services.graph_client import GraphClient


def _slim_item(it: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(it, dict):
        return {}
    file_obj = it.get("file") if isinstance(it.get("file"), dict) else {}
    return {
        "id": it.get("id"),
        "name": it.get("name"),
        "size": it.get("size"),
        "modified": it.get("lastModifiedDateTime"),
        "web_url": it.get("webUrl"),
        "folder": "folder" in it,
        "mime": file_obj.get("mimeType"),
    }


async def list_recent_files(user_id: str, limit: int = 15) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, min(int(limit), 50))
    except (ValueError, TypeError):
        safe_limit = 15
    async with GraphClient(user_id) as g:
        data = await g.get("/me/drive/recent", params={"$top": safe_limit})
        raw_items = (data.get("value") or []) if isinstance(data, dict) else []
        return [_slim_item(i) for i in raw_items if isinstance(i, dict)]


async def search_files(user_id: str, query: str, limit: int = 15) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, min(int(limit), 50))
    except (ValueError, TypeError):
        safe_limit = 15
    # OData string literals must have single quotes escaped by doubling them.
    safe_query = str(query or "").replace("'", "''")
    async with GraphClient(user_id) as g:
        data = await g.get(
            f"/me/drive/root/search(q='{safe_query}')",
            params={"$top": safe_limit},
        )
        raw_items = (data.get("value") or []) if isinstance(data, dict) else []
        return [_slim_item(i) for i in raw_items if isinstance(i, dict)]


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
        return _slim_item(data) if isinstance(data, dict) else {"status": "uploaded", "name": filename}


async def read_file_text(user_id: str, item_id: str) -> dict[str, Any]:
    async with GraphClient(user_id) as g:
        meta = await g.get(f"/me/drive/items/{item_id}")
        meta_dict = meta if isinstance(meta, dict) else {}
        # Reuse the GraphClient session so we inherit throttling + retry.
        content = await g.get_bytes(f"/me/drive/items/{item_id}/content")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = f"<binary {len(content)} bytes>"
        return {**_slim_item(meta_dict), "content": text}
