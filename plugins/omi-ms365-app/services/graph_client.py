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
# Ceiling on @odata.nextLink pages per collection fetch. max_items is the
# intended result bound; this only stops a malformed or runaway nextLink
# chain from paging forever (Graph may return short pages, so keep headroom
# above max_items / page_size).
MAX_PAGES = 50


class GraphError(Exception):
    def __init__(self, status: int, payload: Any) -> None:
        super().__init__(f"Graph {status}: {payload}")
        self.status = status
        self.payload = payload


def _parse_retry_after(header_val: str | None, default: int = 2) -> int:
    """Safely parse Retry-After header (seconds or RFC 7231 HTTP-date)."""
    if not header_val:
        return default
    try:
        return max(1, int(header_val))
    except (ValueError, TypeError):
        pass
    try:
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(header_val)
        now = datetime.now(timezone.utc)
        delta = (dt - now).total_seconds()
        return max(1, int(delta)) if delta > 0 else default
    except Exception:
        return default


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
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"), default=2)
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
        params: dict[str, Any] | None = None,
        *,
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch every page of a Graph collection by following @odata.nextLink.

        ``$top`` is a page size, not a result cap — without this walk a
        collection silently drops every item past the first page. ``params``
        are sent with the first request only: a nextLink already carries the
        query options and repeating them is a Graph error. ``MAX_PAGES``
        plus repeat-link detection keep a malformed or self-referencing
        nextLink from looping forever; ``max_items`` caps collected items.
        """
        if max_items is not None and max_items <= 0:
            return []
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        url: str | None = path
        pages = 0
        while url:
            # nextLink values are absolute; normalise the first page's
            # relative path so a link back to it is still caught as a repeat.
            key = url if url.startswith("http") else f"{GRAPH_BASE}{url}"
            if key in seen:
                log.warning(
                    "Graph nextLink loop on %s — stopping at %d pages", path, pages
                )
                break
            if pages >= MAX_PAGES:
                log.warning("Graph pagination hit MAX_PAGES=%d on %s", MAX_PAGES, path)
                break
            seen.add(key)
            data = await self.get(url, params=params)
            # A nextLink already carries the query options; repeating them is
            # a Graph error, so params go with the first request only.
            params = None
            pages += 1
            if not isinstance(data, dict):
                break
            items.extend(data.get("value") or [])
            if max_items is not None and len(items) >= max_items:
                break
            url = data.get("@odata.nextLink")
        if max_items is not None:
            items = items[:max_items]
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
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"), default=2)
                # Honour the server cooldown; do not shorten a long Retry-After.
                backoff = max(retry_after, min(2 ** attempt + 1, 30))
                log.warning("Graph %s on %s (bytes) — backing off %ss", resp.status_code, path, backoff)
                await asyncio.sleep(backoff)
                continue

            if resp.status_code >= 400:
                raise GraphError(resp.status_code, resp.text)
            return resp.content

        raise GraphError(0, "Exhausted retries without response")

