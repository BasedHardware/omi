"""HTTP client for the Omi Developer API."""

import requests

from omi_manager.config import get_api_key, get_base_url


class OmiClient:
    """Wraps the Omi Developer API (/v1/dev/user/*)."""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or get_api_key()
        self.base_url = (base_url or get_base_url()).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        resp = self.session.request(method, self._url(path), **kwargs)
        if resp.status_code == 204:
            return {"success": True}
        if not resp.ok:
            detail = ""
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise SystemExit(f"API error ({resp.status_code}): {detail}")
        return resp.json()

    # ── Memories ─────────────────────────────────────────

    def list_memories(self, limit: int = 25, offset: int = 0, categories: str = None) -> list:
        params = {"limit": limit, "offset": offset}
        if categories:
            params["categories"] = categories
        return self._request("GET", "/v1/dev/user/memories", params=params)

    def create_memory(self, content: str, category: str = None, visibility: str = "private", tags: list = None) -> dict:
        body = {"content": content, "visibility": visibility, "tags": tags or []}
        if category:
            body["category"] = category
        return self._request("POST", "/v1/dev/user/memories", json=body)

    def update_memory(self, memory_id: str, content: str = None, visibility: str = None, tags: list = None, category: str = None) -> dict:
        body = {}
        if content is not None:
            body["content"] = content
        if visibility is not None:
            body["visibility"] = visibility
        if tags is not None:
            body["tags"] = tags
        if category is not None:
            body["category"] = category
        return self._request("PATCH", f"/v1/dev/user/memories/{memory_id}", json=body)

    def delete_memory(self, memory_id: str) -> dict:
        return self._request("DELETE", f"/v1/dev/user/memories/{memory_id}")

    # ── Action Items (Tasks) ─────────────────────────────

    def list_action_items(self, completed: bool = None, limit: int = 100, offset: int = 0) -> list:
        params = {"limit": limit, "offset": offset}
        if completed is not None:
            params["completed"] = str(completed).lower()
        return self._request("GET", "/v1/dev/user/action-items", params=params)

    def create_action_item(self, description: str, due_at: str = None) -> dict:
        body = {"description": description, "completed": False}
        if due_at:
            body["due_at"] = due_at
        return self._request("POST", "/v1/dev/user/action-items", json=body)

    def update_action_item(self, item_id: str, description: str = None, completed: bool = None, due_at: str = None) -> dict:
        body = {}
        if description is not None:
            body["description"] = description
        if completed is not None:
            body["completed"] = completed
        if due_at is not None:
            body["due_at"] = due_at
        return self._request("PATCH", f"/v1/dev/user/action-items/{item_id}", json=body)

    def delete_action_item(self, item_id: str) -> dict:
        return self._request("DELETE", f"/v1/dev/user/action-items/{item_id}")

    # ── Conversations ────────────────────────────────────

    def list_conversations(self, limit: int = 25, offset: int = 0) -> list:
        params = {"limit": limit, "offset": offset}
        return self._request("GET", "/v1/dev/user/conversations", params=params)

    def get_conversation(self, conversation_id: str) -> dict:
        return self._request("GET", f"/v1/dev/user/conversations/{conversation_id}")

    def create_conversation(self, text: str, text_source: str = "other", language: str = "en") -> dict:
        body = {"text": text, "text_source": text_source, "language": language}
        return self._request("POST", "/v1/dev/user/conversations", json=body)

    def delete_conversation(self, conversation_id: str) -> dict:
        return self._request("DELETE", f"/v1/dev/user/conversations/{conversation_id}")
