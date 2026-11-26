"""The one public address of a prod-parity stack.

Production puts a load balancer in front of several services that all run the
same backend image with different settings: websockets go to ``backend-listen``,
offline uploads to ``backend-sync``, everything else to ``backend``. A client
knows one base URL. This module is that front door for the harness: a plain
pass-through that picks the upstream by request, so each request is handled by
the process carrying that production service's settings.

It adds nothing a client can observe beyond the hop itself: no retries, no
timeouts, no buffering of bodies, close codes relayed both ways. The exact
production URL map is not in the repository. With a production snapshot the
router uses the load balancer's own path rules (``OMI_HARNESS_EDGE_ROUTES``):
an exact path, or a ``/*`` suffix for a prefix, most specific first, anything
else to the default service, for HTTP and websockets alike. That is how
production sends an upload to ``backend-sync`` and the status poll for the same
job to ``backend``. Without a snapshot it falls back to ``SYNC_PREFIXES``, an
approximation from ``backend/docs/runbooks/sync-two-lane.md``: the upload
routes go to sync whole, including their status polls.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Awaitable, Callable

from dev_harness import log_timestamps

BACKEND_ENV = "OMI_HARNESS_EDGE_BACKEND_URL"
LISTEN_ENV = "OMI_HARNESS_EDGE_LISTEN_URL"
SYNC_ENV = "OMI_HARNESS_EDGE_SYNC_URL"
INTEGRATION_ENV = "OMI_HARNESS_EDGE_INTEGRATION_URL"
ROUTES_ENV = "OMI_HARNESS_EDGE_ROUTES"
# Load balancer backend -> the router's upstream name.
_UPSTREAM_OF_SERVICE = {
    "backend": "backend",
    "backend-sync": "sync",
    "backend-listen": "listen",
    "backend-integration": "integration",
}

SYNC_PREFIXES = (
    "/v1/sync-local-files",
    "/v2/sync-local-files",
    "/v2/sync-capture-manifest",
    "/v2/sync-capture-end",
    "/v1/sync/",
)
_HOP_BY_HOP = {
    b"connection",
    b"keep-alive",
    b"proxy-authenticate",
    b"proxy-authorization",
    b"te",
    b"trailers",
    b"transfer-encoding",
    b"upgrade",
    b"host",
}
_WEBSOCKET_HANDSHAKE = {
    b"sec-websocket-key",
    b"sec-websocket-version",
    b"sec-websocket-extensions",
    b"sec-websocket-protocol",
}

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


def route_matches(pattern: str, path: str) -> bool:
    """A Google load balancer path rule: exact, or ``/prefix/*`` for anything under the prefix."""
    if pattern.endswith("/*"):
        return path.startswith(pattern[:-1])
    return path == pattern


def upstream_for_routes(routes: list[tuple[str, str]], default: str, path: str) -> str:
    """The first matching rule (callers pass them most specific first), else the default."""
    for pattern, upstream in routes:
        if route_matches(pattern, path):
            return upstream
    return default


def upstream_for(scope_type: str, path: str) -> str:
    """Which production service takes this request: ``listen``, ``sync`` or ``backend``."""
    if scope_type == "websocket":
        return "listen"
    if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in SYNC_PREFIXES):
        return "sync"
    return "backend"


def _forwarded_headers(scope: Scope, drop: set[bytes]) -> list[tuple[str, str]]:
    headers = [
        (name.decode("latin-1"), value.decode("latin-1"))
        for name, value in scope.get("headers", [])
        if name.lower() not in drop
    ]
    client = scope.get("client")
    if client:
        headers.append(("x-forwarded-for", str(client[0])))
    return headers


class EdgeRouter:
    def __init__(
        self, upstreams: dict[str, str], routes: list[tuple[str, str]] | None = None, default: str = "backend"
    ):
        self._upstreams = {name: url.rstrip("/") for name, url in upstreams.items()}
        self._routes, self._default = routes, default
        self._client: Any = None

    def _upstream(self, scope_type: str, path: str) -> str:
        if self._routes is None:
            return upstream_for(scope_type, path)
        return upstream_for_routes(self._routes, self._default, path)

    def _http_client(self) -> Any:
        if self._client is None:
            import httpx

            verify: Any = os.environ.get("OMI_HARNESS_CA_BUNDLE", "").strip() or True
            self._client = httpx.AsyncClient(
                verify=verify,
                timeout=None,
                limits=httpx.Limits(max_connections=None, max_keepalive_connections=64),
                trust_env=False,
            )
            # A pass-through sends the client's headers and nothing of its own
            # (httpx would add Accept-Encoding, which changes the response body).
            for name in ("accept", "accept-encoding", "user-agent", "connection"):
                del self._client.headers[name]
        return self._client

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    if self._client is not None:
                        await self._client.aclose()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        name = self._upstream(scope["type"], scope.get("path", ""))
        started = time.monotonic()
        outcome = "no_response"
        try:
            if scope["type"] == "websocket":
                outcome = await self._websocket(scope, receive, send, self._upstreams[name])
            else:
                outcome = await self._http(scope, receive, send, self._upstreams[name])
        except BaseException as error:
            outcome = f"exception:{type(error).__name__}"
            raise
        finally:
            client = scope.get("client")
            print(
                log_timestamps.line(
                    f"harness_edge kind={scope['type']} method={scope.get('method', 'WS')} "
                    f"path={scope.get('path', '')} upstream={name} status={outcome} "
                    f"ms={int((time.monotonic() - started) * 1000)} client={client[0] if client else 'unknown'}"
                ),
                flush=True,
            )

    async def _http(self, scope: Scope, receive: Receive, send: Send, base: str) -> str:
        import httpx

        query = scope.get("query_string", b"").decode("latin-1")
        url = base + scope["path"] + (f"?{query}" if query else "")

        async def body() -> Any:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    raise httpx.RequestError("client disconnected")
                chunk = message.get("body", b"")
                if chunk:
                    yield chunk
                if not message.get("more_body", False):
                    return

        request = self._http_client().build_request(
            scope["method"], url, headers=_forwarded_headers(scope, _HOP_BY_HOP), content=body()
        )
        try:
            response = await self._http_client().send(request, stream=True)
        except httpx.ConnectError:
            await send({"type": "http.response.start", "status": 502, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return "502"
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": response.status_code,
                    "headers": [
                        (name.lower(), value) for name, value in response.headers.raw if name.lower() not in _HOP_BY_HOP
                    ],
                }
            )
            async for chunk in response.aiter_raw():
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b""})
        finally:
            await response.aclose()
        return str(response.status_code)

    async def _websocket(self, scope: Scope, receive: Receive, send: Send, base: str) -> str:
        import websockets
        from websockets.exceptions import ConnectionClosed, InvalidStatusCode

        first = await receive()
        if first["type"] != "websocket.connect":
            return "not_connect"
        query = scope.get("query_string", b"").decode("latin-1")
        url = "ws" + base[len("http") :] + scope["path"] + (f"?{query}" if query else "")
        try:
            upstream = await websockets.connect(
                url,
                extra_headers=_forwarded_headers(scope, _HOP_BY_HOP | _WEBSOCKET_HANDSHAKE),
                subprotocols=scope.get("subprotocols") or None,
                max_size=None,
                ping_interval=None,  # keepalive belongs to the two real endpoints
                open_timeout=None,
                compression=None,
            )
        except InvalidStatusCode as error:
            if "websocket.http.response" in scope.get("extensions", {}):
                await send({"type": "websocket.http.response.start", "status": error.status_code, "headers": []})
                await send({"type": "websocket.http.response.body", "body": b""})
            else:
                await send({"type": "websocket.close", "code": 1008})
            return f"refused:{error.status_code}"
        except OSError:
            await send({"type": "websocket.close", "code": 1013})
            return "upstream_unreachable"
        await send({"type": "websocket.accept", "subprotocol": upstream.subprotocol})
        outcome = "closed"

        client_gone = False

        async def client_to_upstream() -> str:
            nonlocal client_gone
            while True:
                message = await receive()
                if message["type"] == "websocket.disconnect":
                    client_gone = True
                    code = message.get("code", 1005)
                    await upstream.close(code if 1000 <= code <= 4999 and code not in (1005, 1006) else 1000)
                    return f"client_closed:{code}"
                data = message.get("bytes")
                await upstream.send(data if data is not None else message.get("text", ""))

        async def upstream_to_client() -> str:
            try:
                async for data in upstream:
                    if isinstance(data, (bytes, bytearray)):
                        await send({"type": "websocket.send", "bytes": bytes(data)})
                    else:
                        await send({"type": "websocket.send", "text": data})
            except ConnectionClosed:
                pass
            code = upstream.close_code or 1006
            if not client_gone:  # the upstream ended the session; hand its close code to the client
                await send(
                    {
                        "type": "websocket.close",
                        "code": code if code not in (1005, 1006) else 1011,
                        "reason": upstream.close_reason or "",
                    }
                )
            return f"closed:{code}"

        tasks = [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            # Whoever ended the session names the outcome: the client's side when it left first.
            first = tasks[0] if tasks[0] in done else tasks[1]
            outcome = first.result()
        finally:
            await upstream.close()
        return outcome


def _from_env() -> EdgeRouter:
    upstreams = {
        "backend": os.environ.get(BACKEND_ENV, ""),
        "listen": os.environ.get(LISTEN_ENV, ""),
        "sync": os.environ.get(SYNC_ENV, ""),
    }
    missing = [name for name, url in upstreams.items() if not url]
    if missing:
        raise RuntimeError(f"edge router upstreams are not configured: {', '.join(missing)}")
    raw = os.environ.get(ROUTES_ENV, "").strip()
    if not raw:
        return EdgeRouter(upstreams)
    document = json.loads(raw)
    upstreams["integration"] = os.environ.get(INTEGRATION_ENV, "")
    routes = [(pattern, _UPSTREAM_OF_SERVICE[service]) for pattern, service in document["routes"]]
    default = _UPSTREAM_OF_SERVICE[document["default"]]
    unknown = sorted(({upstream for _, upstream in routes} | {default}) - {n for n, url in upstreams.items() if url})
    if unknown:
        raise RuntimeError(f"edge routes name upstreams with no address: {', '.join(unknown)}")
    print(f"harness_edge event=routes source=production_snapshot rules={len(routes)} default={default}", flush=True)
    return EdgeRouter(upstreams, routes, default)


def __getattr__(name: str) -> Any:
    # ``uvicorn dev_harness.edge_router:app`` builds the router from the environment
    # on first use; importing the module for its routing table needs no upstreams.
    if name == "app":
        globals()["app"] = _from_env()
        return globals()["app"]
    raise AttributeError(name)
