"""Thin async Microsoft Graph client with throttling-aware retry."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from services.auth import get_access_token

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RETRIES = 3
# Upper bound on pages a single get_all() will walk. Graph collections are
# server-paged and $top is a page size, not a result cap, so a caller asking
# for "everything" must follow @odata.nextLink; this keeps a malformed or
# self-referencing nextLink from turning that into an infinite loop.
MAX_PAGES = 20


class GraphError(Exception):
    def __init__(self, status: int, payload: Any) -> None:
        super().__init__(f"Graph {status}: {payload}")
        self.status = status
        self.payload = payload


class GraphClient:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self) -> "GraphClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        expect_json: bool = True,
    ) -> Any:
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"

        for attempt in range(MAX_RETRIES):
            token = await get_access_token(self.user_id)
            headers = {"Authorization": f"Bearer {token}"}
            if json is not None:
                headers["Content-Type"] = "application/json"

            resp = await self._client.request(
                method, url, headers=headers, params=params, json=json
            )

            # Throttling: honour Retry-After
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == MAX_RETRIES - 1:
                    raise GraphError(resp.status_code, resp.text)
                retry_after = int(resp.headers.get("Retry-After", "2"))
                # Honour the server cooldown; do not shorten a long Retry-After.
                backoff = max(retry_after, min(2 ** attempt + 1, 30))
                log.warning("Graph %s on %s — backing off %ss", resp.status_code, path, backoff)
                await asyncio.sleep(backoff)
                continue

            if resp.status_code >= 400:
                payload: Any
                try:
                    payload = resp.json()
                except Exception:
                    payload = resp.text
                raise GraphError(resp.status_code, payload)

            if not expect_json or resp.status_code == 204:
                return None
            return resp.json()

        raise GraphError(0, "Exhausted retries without response")

    # Public convenience wrappers ---------------------------------------------

    async def get(self, path: str, **kw: Any) -> Any:
        return await self._request("GET", path, **kw)

    async def get_all(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        """GET a collection and follow ``@odata.nextLink`` until Graph runs out.

        Graph returns at most one page per request regardless of ``$top``;
        the rest arrives only by requesting the ``@odata.nextLink`` it hands
        back. That link already carries every query option (``$top``,
        ``$filter``, ``$orderby``, ``startDateTime``…), so ``params`` are sent
        with the first request only — repeating them on a nextLink makes Graph
        reject the request.
        """
        items: list[dict[str, Any]] = []
        url = path
        first = True
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            data = await self.get(url, params=params if first else None)
            first = False
            items.extend(data.get("value") or [])
            if max_items is not None and len(items) >= max_items:
                return items[:max_items]
            url = data.get("@odata.nextLink")
            if not url:
                return items
            if url in seen:
                log.warning("Graph returned a repeating @odata.nextLink for %s — stopping", path)
                return items
            seen.add(url)
        log.warning("Graph collection %s exceeded %d pages — returning what was read", path, MAX_PAGES)
        return items

    async def post(self, path: str, json: Any, **kw: Any) -> Any:
        return await self._request("POST", path, json=json, **kw)

    async def patch(self, path: str, json: Any, **kw: Any) -> Any:
        return await self._request("PATCH", path, json=json, **kw)

    async def delete(self, path: str, **kw: Any) -> Any:
        return await self._request("DELETE", path, expect_json=False, **kw)

    async def put_bytes(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> Any:
        token = await get_access_token(self.user_id)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": content_type}
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
        resp = await self._client.put(url, headers=headers, content=data)
        if resp.status_code >= 400:
            raise GraphError(resp.status_code, resp.text)
        return resp.json() if resp.content else None


    async def get_bytes(self, path: str) -> bytes:
        """GET raw bytes — used for file content downloads.

        Reuses this client's session + auth so callers don't bypass
        throttling/retry by instantiating their own httpx.AsyncClient.
        """
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"

        for attempt in range(MAX_RETRIES):
            token = await get_access_token(self.user_id)
            headers = {"Authorization": f"Bearer {token}"}
            resp = await self._client.get(url, headers=headers)

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == MAX_RETRIES - 1:
                    raise GraphError(resp.status_code, resp.text)
                retry_after = int(resp.headers.get("Retry-After", "2"))
                # Honour the server cooldown; do not shorten a long Retry-After.
                backoff = max(retry_after, min(2 ** attempt + 1, 30))
                log.warning("Graph %s on %s — backing off %ss", resp.status_code, path, backoff)
                await asyncio.sleep(backoff)
                continue

            if resp.status_code >= 400:
                raise GraphError(resp.status_code, resp.text)
            return resp.content

        raise GraphError(0, "Exhausted retries without response")

