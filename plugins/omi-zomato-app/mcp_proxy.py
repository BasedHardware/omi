"""
MCP proxy client for Zomato.

Handles JSON-RPC communication with Zomato's MCP server, including
session initialization, tool calling, OAuth token refresh, and
SSE transport fallback.
"""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
from typing import Optional
from urllib.parse import urlencode, urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

ZOMATO_MCP_URL = "https://mcp-server.zomato.com/mcp"
MCP_CLIENT_NAME = "Omi"
MCP_CLIENT_VERSION = "1.0.0"
MCP_PROTOCOL_VERSION = "2025-03-26"


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------


async def discover_oauth_metadata(server_url: str) -> Optional[dict]:
    """Discover OAuth metadata from /.well-known/oauth-authorization-server."""
    parsed = urlparse(server_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    metadata_url = urljoin(origin, "/.well-known/oauth-authorization-server")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(metadata_url, follow_redirects=True)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "authorization_endpoint": data.get("authorization_endpoint"),
                    "token_endpoint": data.get("token_endpoint"),
                    "registration_endpoint": data.get("registration_endpoint"),
                    "scopes_supported": data.get("scopes_supported", []),
                }
        except Exception:
            pass
    return None


async def register_oauth_client(registration_endpoint: str, redirect_uri: str, scopes: Optional[list] = None) -> dict:
    """Dynamically register an OAuth client (RFC 7591)."""
    payload = {
        "client_name": MCP_CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if scopes:
        payload["scope"] = " ".join(scopes)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(registration_endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "client_id": data["client_id"],
            "client_secret": data.get("client_secret"),
        }


def generate_pkce_pair() -> tuple:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def build_authorization_url(
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: Optional[list] = None,
    code_challenge: Optional[str] = None,
) -> str:
    """Build the OAuth authorization URL."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    if scopes:
        params["scope"] = " ".join(scopes)
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    return f"{authorization_endpoint}?{urlencode(params)}"


async def exchange_oauth_code(
    token_endpoint: str,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: Optional[str] = None,
    code_verifier: Optional[str] = None,
) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    if code_verifier:
        payload["code_verifier"] = code_verifier

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_endpoint, data=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in"),
        }


async def refresh_oauth_token(
    token_endpoint: str,
    refresh_token: str,
    client_id: str,
    client_secret: Optional[str] = None,
) -> dict:
    """Refresh an expired access token."""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_endpoint, data=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": data.get("expires_in"),
        }


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _jsonrpc_request(method: str, params: Optional[dict] = None, req_id: Optional[int] = None) -> dict:
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if req_id is not None:
        msg["id"] = req_id
    return msg


async def _mcp_post(
    server_url: str,
    payload: dict,
    access_token: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple:
    """Send a JSON-RPC request via Streamable HTTP. Returns (response_dict, session_id)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        resp = await client.post(server_url, json=payload, headers=headers, follow_redirects=True)

        if resp.status_code == 401:
            raise PermissionError("MCP server returned 401 Unauthorized")

        new_session_id = resp.headers.get("mcp-session-id", session_id)

        if resp.status_code in (202, 204) or not resp.text.strip():
            return {}, new_session_id

        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return _parse_sse_response(resp.text), new_session_id

        return resp.json(), new_session_id


def _parse_sse_response(text: str) -> dict:
    """Parse an SSE response and extract the last JSON-RPC result."""
    last_data = None
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str:
                try:
                    last_data = json.loads(data_str)
                except (json.JSONDecodeError, ValueError):
                    pass
    if last_data:
        return last_data
    return {}


# ---------------------------------------------------------------------------
# SSE transport
# ---------------------------------------------------------------------------


async def _sse_send_and_receive(
    sse_url: str,
    payloads: list,
    access_token: Optional[str] = None,
    timeout_seconds: float = 30.0,
) -> list:
    """Send JSON-RPC requests via SSE transport and collect responses."""
    return await asyncio.wait_for(
        _sse_send_and_receive_inner(sse_url, payloads, access_token),
        timeout=timeout_seconds,
    )


async def _sse_send_and_receive_inner(
    sse_url: str,
    payloads: list,
    access_token: Optional[str] = None,
) -> list:
    parsed = urlparse(sse_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    headers = {"Accept": "text/event-stream"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    expected_responses = sum(1 for p in payloads if "id" in p)
    responses = []
    post_endpoint = None

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        async with client.stream("GET", sse_url, headers=headers, follow_redirects=True) as stream:
            if stream.status_code == 401:
                raise PermissionError("MCP server returned 401 Unauthorized")
            if stream.status_code >= 400:
                await stream.aread()
                raise httpx.HTTPStatusError(
                    f"SSE connection failed with {stream.status_code}",
                    request=stream._request,
                    response=httpx.Response(stream.status_code),
                )

            buf = ""
            event_type = ""
            event_data_lines = []

            async for raw_chunk in stream.aiter_text():
                buf += raw_chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        event_data_lines.append(line[5:].strip())
                    elif line == "":
                        data_str = "\n".join(event_data_lines)
                        event_data_lines = []

                        if event_type == "endpoint" and data_str:
                            if data_str.startswith("http"):
                                post_endpoint = data_str
                            else:
                                post_endpoint = origin + data_str

                            post_headers = {"Content-Type": "application/json"}
                            if access_token:
                                post_headers["Authorization"] = f"Bearer {access_token}"
                            for payload in payloads:
                                await client.post(
                                    post_endpoint, json=payload, headers=post_headers, follow_redirects=True
                                )

                        elif event_type == "message" and data_str:
                            try:
                                msg = json.loads(data_str)
                                if isinstance(msg, dict) and ("result" in msg or "error" in msg):
                                    responses.append(msg)
                            except (json.JSONDecodeError, ValueError):
                                pass

                        event_type = ""

                        if len(responses) >= expected_responses:
                            return responses

    return responses


# ---------------------------------------------------------------------------
# MCP session & tool calling
# ---------------------------------------------------------------------------


async def _initialize_session(server_url: str, access_token: Optional[str] = None) -> Optional[str]:
    """Establish MCP session (initialize + notifications/initialized)."""
    init_req = _jsonrpc_request(
        "initialize",
        params={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": MCP_CLIENT_NAME, "version": MCP_CLIENT_VERSION},
        },
        req_id=1,
    )
    _, session_id = await _mcp_post(server_url, init_req, access_token)

    notif = _jsonrpc_request("notifications/initialized")
    try:
        _, session_id = await _mcp_post(server_url, notif, access_token, session_id)
    except Exception:
        pass

    return session_id


def _extract_tool_result(resp: dict) -> str:
    """Extract text result from a JSON-RPC tool call response."""
    result = resp.get("result", {})

    content = result.get("content", [])
    texts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(item.get("text", ""))
    if texts:
        return "\n".join(texts)

    if result:
        return str(result)
    if resp.get("error"):
        return f"MCP error: {resp['error'].get('message', str(resp['error']))}"
    return "No result returned from MCP tool."


def _resolve_mcp_url(server_url: str) -> list:
    parsed = urlparse(server_url)
    path = parsed.path.rstrip("/")
    if path in ("", "/"):
        base = server_url.rstrip("/")
        return [base, f"{base}/http", f"{base}/sse"]
    return [server_url]


def _resolve_sse_url(server_url: str) -> list:
    parsed = urlparse(server_url)
    path = parsed.path.rstrip("/")
    base = server_url.rstrip("/")
    if path in ("", "/"):
        return [f"{base}/sse", base]
    if path == "/sse":
        return [server_url]
    return [server_url, f"{base}/sse"]


async def call_zomato_tool(tool_name: str, arguments: dict, access_token: str, oauth_tokens: dict) -> str:
    """Call a Zomato MCP tool. Tries Streamable HTTP first, then SSE.

    Handles 401 by refreshing the token and retrying once.
    Returns the tool result as a string, or updated tokens dict via oauth_tokens mutation.
    """
    server_url = ZOMATO_MCP_URL

    # --- Attempt Streamable HTTP ---
    candidates = _resolve_mcp_url(server_url)
    req = _jsonrpc_request("tools/call", params={"name": tool_name, "arguments": arguments}, req_id=3)

    for url in candidates:
        try:
            session_id = await _initialize_session(url, access_token)
            resp, _ = await _mcp_post(url, req, access_token, session_id)
            return _extract_tool_result(resp)
        except PermissionError:
            # Try refresh
            refreshed = await _try_refresh(oauth_tokens)
            if refreshed:
                try:
                    session_id = await _initialize_session(url, refreshed["access_token"])
                    resp, _ = await _mcp_post(url, req, refreshed["access_token"], session_id)
                    return _extract_tool_result(resp)
                except Exception as e:
                    logger.error(f"[Zomato MCP] Retry after refresh failed: {e}")
            return "Error: Zomato returned 401 Unauthorized. Please re-authenticate."
        except Exception as e:
            logger.warning(f"[Zomato MCP] Streamable HTTP failed at {url}: {e}")
            continue

    # --- Attempt SSE ---
    sse_candidates = _resolve_sse_url(server_url)
    for url in sse_candidates:
        try:
            init_req = _jsonrpc_request(
                "initialize",
                params={
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": MCP_CLIENT_NAME, "version": MCP_CLIENT_VERSION},
                },
                req_id=1,
            )
            notif = _jsonrpc_request("notifications/initialized")
            call_req = _jsonrpc_request("tools/call", params={"name": tool_name, "arguments": arguments}, req_id=3)

            responses = await _sse_send_and_receive(url, [init_req, notif, call_req], access_token)

            for r in responses:
                if r.get("id") == 3:
                    return _extract_tool_result(r)
            if responses:
                return _extract_tool_result(responses[-1])
        except PermissionError:
            refreshed = await _try_refresh(oauth_tokens)
            if refreshed:
                try:
                    responses = await _sse_send_and_receive(url, [init_req, notif, call_req], refreshed["access_token"])
                    for r in responses:
                        if r.get("id") == 3:
                            return _extract_tool_result(r)
                    if responses:
                        return _extract_tool_result(responses[-1])
                except Exception:
                    pass
            return "Error: Zomato returned 401 Unauthorized. Please re-authenticate."
        except Exception as e:
            logger.warning(f"[Zomato MCP] SSE failed at {url}: {e}")
            continue

    return f"Error: Failed to connect to Zomato MCP server at {server_url}"


async def discover_tools(access_token: Optional[str] = None) -> list:
    """Discover available tools from Zomato's MCP server. Returns list of raw tool dicts."""
    server_url = ZOMATO_MCP_URL
    candidates = _resolve_mcp_url(server_url)

    # Try Streamable HTTP
    for url in candidates:
        try:
            session_id = await _initialize_session(url, access_token)
            tools_req = _jsonrpc_request("tools/list", params={}, req_id=2)
            tools_resp, _ = await _mcp_post(url, tools_req, access_token, session_id)
            tools = tools_resp.get("result", {}).get("tools", [])
            if tools:
                return tools
        except Exception:
            continue

    # Try SSE
    sse_candidates = _resolve_sse_url(server_url)
    for url in sse_candidates:
        try:
            init_req = _jsonrpc_request(
                "initialize",
                params={
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": MCP_CLIENT_NAME, "version": MCP_CLIENT_VERSION},
                },
                req_id=1,
            )
            notif = _jsonrpc_request("notifications/initialized")
            tools_req = _jsonrpc_request("tools/list", params={}, req_id=2)

            responses = await _sse_send_and_receive(url, [init_req, notif, tools_req], access_token)
            for r in responses:
                if r.get("id") == 2:
                    tools = r.get("result", {}).get("tools", [])
                    if tools:
                        return tools
        except Exception:
            continue

    return []


async def _try_refresh(oauth_tokens: dict) -> Optional[dict]:
    """Attempt to refresh the access token. Updates oauth_tokens in place and returns new tokens."""
    refresh_token = oauth_tokens.get("refresh_token")
    token_endpoint = oauth_tokens.get("token_endpoint")
    client_id = oauth_tokens.get("client_id")

    if not all([refresh_token, token_endpoint, client_id]):
        return None

    try:
        new_tokens = await refresh_oauth_token(
            token_endpoint, refresh_token, client_id, oauth_tokens.get("client_secret")
        )
        oauth_tokens["access_token"] = new_tokens["access_token"]
        if new_tokens.get("refresh_token"):
            oauth_tokens["refresh_token"] = new_tokens["refresh_token"]
        if new_tokens.get("expires_in"):
            oauth_tokens["expires_at"] = time.time() + new_tokens["expires_in"]
        return oauth_tokens
    except Exception as e:
        logger.error(f"[Zomato MCP] Token refresh failed: {e}")
        return None
