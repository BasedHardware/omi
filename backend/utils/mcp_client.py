"""
MCP (Model Context Protocol) client for connecting to remote MCP servers.

Handles:
- OAuth metadata discovery and authorization flow
- MCP tool discovery via JSON-RPC (initialize + tools/list)
- MCP tool execution via JSON-RPC (tools/call)
- Brandfetch logo fetching
"""

import asyncio
import base64
import hashlib
import json
import secrets
import time
from typing import Optional
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from models.app import ChatTool

MCP_CLIENT_NAME = "Omi"
MCP_CLIENT_VERSION = "1.0.0"
MCP_PROTOCOL_VERSION = "2025-03-26"


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------


async def discover_oauth_metadata(server_url: str) -> Optional[dict]:
    """Discover OAuth authorization server metadata from an MCP server.

    Checks /.well-known/oauth-authorization-server relative to the server origin.
    Returns metadata dict or None if the server does not require OAuth.
    """
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
    """Dynamically register an OAuth client (RFC 7591).

    Returns dict with client_id and optionally client_secret.
    """
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
        print(f"[MCP OAuth] Registration response: {data}")
        return {
            "client_id": data["client_id"],
            "client_secret": data.get("client_secret"),
        }


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256).

    Returns (code_verifier, code_challenge).
    """
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
    """Build the authorization URL for the OAuth flow."""
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
    """Exchange an authorization code for access + refresh tokens."""
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
        token_type = data.get("token_type", "Bearer")
        has_access = bool(data.get("access_token"))
        has_refresh = bool(data.get("refresh_token"))
        expires_in = data.get("expires_in")
        print(
            f"[MCP OAuth] Token exchange OK: type={token_type}, has_access={has_access}, has_refresh={has_refresh}, expires_in={expires_in}"
        )
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in"),
            "token_type": token_type,
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
            "token_type": data.get("token_type", "Bearer"),
        }


# ---------------------------------------------------------------------------
# MCP JSON-RPC helpers
# ---------------------------------------------------------------------------


def _jsonrpc_request(method: str, params: Optional[dict] = None, req_id: Optional[int] = None) -> dict:
    msg = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        msg["params"] = params
    if req_id is not None:
        msg["id"] = req_id
    return msg


def _resolve_mcp_url(server_url: str) -> list[str]:
    """Return a list of candidate URLs to try for an MCP server.

    Many MCP servers expose their Streamable HTTP transport at /http or /sse
    rather than at the root. If the user provides just the origin (no path or
    path is /), we generate candidates with the common suffixes so that tool
    discovery and invocation succeed without requiring the user to know the
    exact path.
    """
    parsed = urlparse(server_url)
    path = parsed.path.rstrip("/")
    if path in ("", "/"):
        base = server_url.rstrip("/")
        return [base, f"{base}/http", f"{base}/sse"]
    return [server_url]


async def _mcp_post(
    server_url: str,
    payload: dict,
    access_token: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[dict, Optional[str]]:
    """Send a JSON-RPC request to an MCP server via Streamable HTTP.

    Returns (response_dict, session_id). The session_id may be updated from the
    Mcp-Session-Id response header and should be passed to subsequent requests.
    """
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

        # Capture session ID from response
        new_session_id = resp.headers.get("mcp-session-id", session_id)

        # Notifications (no "id" in request) may return 202/204 with no body
        if resp.status_code in (202, 204) or not resp.text.strip():
            return {}, new_session_id

        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        # Handle SSE response
        if "text/event-stream" in content_type:
            return _parse_sse_response(resp.text), new_session_id

        # Handle plain JSON response
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
# SSE transport helpers
# ---------------------------------------------------------------------------


async def _sse_send_and_receive(
    sse_url: str,
    payloads: list[dict],
    access_token: Optional[str] = None,
    timeout_seconds: float = 30.0,
) -> list[dict]:
    """Send JSON-RPC requests via the MCP SSE transport and collect responses.

    Opens a GET connection to the SSE endpoint, waits for the endpoint event,
    then POSTs each payload to the advertised endpoint URL and collects
    JSON-RPC responses from the SSE stream.

    Returns a list of JSON-RPC response dicts (one per payload that has an id).
    """
    return await asyncio.wait_for(
        _sse_send_and_receive_inner(sse_url, payloads, access_token),
        timeout=timeout_seconds,
    )


async def _sse_send_and_receive_inner(
    sse_url: str,
    payloads: list[dict],
    access_token: Optional[str] = None,
) -> list[dict]:
    """Inner SSE implementation wrapped by _sse_send_and_receive with a timeout."""
    parsed = urlparse(sse_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    headers = {"Accept": "text/event-stream"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    expected_responses = sum(1 for p in payloads if "id" in p)
    responses: list[dict] = []
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

            print(f"[MCP SSE] Connected to {sse_url}, status={stream.status_code}")
            buf = ""
            event_type = ""
            event_data_lines: list[str] = []

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
                        # End of event
                        data_str = "\n".join(event_data_lines)
                        event_data_lines = []

                        if event_type == "endpoint" and data_str:
                            # Endpoint may be relative or absolute
                            if data_str.startswith("http"):
                                post_endpoint = data_str
                            else:
                                post_endpoint = origin + data_str
                            print(f"[MCP SSE] Got endpoint: {post_endpoint}")

                            # Now send all payloads
                            post_headers = {"Content-Type": "application/json"}
                            if access_token:
                                post_headers["Authorization"] = f"Bearer {access_token}"
                            for payload in payloads:
                                await client.post(
                                    post_endpoint,
                                    json=payload,
                                    headers=post_headers,
                                    follow_redirects=True,
                                )

                        elif event_type == "message" and data_str:
                            try:
                                msg = json.loads(data_str)
                                if isinstance(msg, dict) and ("result" in msg or "error" in msg):
                                    responses.append(msg)
                                    print(f"[MCP SSE] Got response {len(responses)}/{expected_responses}")
                            except (json.JSONDecodeError, ValueError):
                                pass

                        event_type = ""

                        if len(responses) >= expected_responses:
                            return responses

    if not post_endpoint:
        raise Exception(f"SSE endpoint at {sse_url} did not advertise a POST endpoint")
    return responses


async def _discover_tools_via_sse(sse_url: str, access_token: Optional[str] = None) -> list[dict]:
    """Discover MCP tools using SSE transport.

    Sends initialize + notifications/initialized + tools/list via SSE and returns
    the raw tool dicts from the server.
    """
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

    responses = await _sse_send_and_receive(
        sse_url,
        [init_req, notif, tools_req],
        access_token,
    )

    # Find the tools/list response (id=2)
    for resp in responses:
        if resp.get("id") == 2:
            return resp.get("result", {}).get("tools", [])

    # Fallback: check last response
    if responses:
        return responses[-1].get("result", {}).get("tools", [])
    return []


async def _call_tool_via_sse(
    sse_url: str,
    tool_name: str,
    arguments: dict,
    access_token: Optional[str] = None,
) -> dict:
    """Call an MCP tool using SSE transport. Returns the JSON-RPC response dict."""
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
    call_req = _jsonrpc_request(
        "tools/call",
        params={"name": tool_name, "arguments": arguments},
        req_id=3,
    )

    responses = await _sse_send_and_receive(
        sse_url,
        [init_req, notif, call_req],
        access_token,
    )

    # Find the tools/call response (id=3)
    for resp in responses:
        if resp.get("id") == 3:
            return resp
    if responses:
        return responses[-1]
    return {}


async def discover_mcp_tools(server_url: str, access_token: Optional[str] = None) -> list[ChatTool]:
    """Connect to an MCP server and discover available tools.

    Tries Streamable HTTP transport first (POST-based), then falls back to
    SSE transport (GET event stream + POST to advertised endpoint).
    Returns a list of ChatTool objects with is_mcp=True.
    """
    candidates = _resolve_mcp_url(server_url)
    errors: list[str] = []

    # --- Attempt 1: Streamable HTTP transport ---
    for url in candidates:
        try:
            print(f"[MCP Discovery] Trying Streamable HTTP at {url}")
            session_id = await _initialize_session(url, access_token)

            tools_req = _jsonrpc_request("tools/list", params={}, req_id=2)
            tools_resp, session_id = await _mcp_post(url, tools_req, access_token, session_id)

            result = tools_resp.get("result", {})
            mcp_tools = result.get("tools", [])
            if not mcp_tools:
                raise Exception(f"No tools returned from {url}")

            print(f"[MCP Discovery] Success via Streamable HTTP at {url}, found {len(mcp_tools)} tools")
            return _build_chat_tools(mcp_tools, url, transport="streamable_http")
        except Exception as e:
            print(f"[MCP Discovery] Streamable HTTP failed at {url}: {e}")
            errors.append(f"HTTP {url}: {e}")
            continue

    # --- Attempt 2: SSE transport ---
    sse_candidates = _resolve_sse_url(server_url)
    for url in sse_candidates:
        try:
            print(f"[MCP Discovery] Trying SSE at {url}")
            mcp_tools = await _discover_tools_via_sse(url, access_token)
            if not mcp_tools:
                raise Exception(f"No tools returned from SSE at {url}")

            print(f"[MCP Discovery] Success via SSE at {url}, found {len(mcp_tools)} tools")
            return _build_chat_tools(mcp_tools, url, transport="sse")
        except Exception as e:
            print(f"[MCP Discovery] SSE failed at {url}: {e}")
            errors.append(f"SSE {url}: {e}")
            continue

    error_summary = "; ".join(errors)
    raise Exception(f"Failed to discover tools at {server_url}. Tried: {error_summary}")


def _resolve_sse_url(server_url: str) -> list[str]:
    """Return candidate SSE endpoint URLs."""
    parsed = urlparse(server_url)
    path = parsed.path.rstrip("/")
    base = server_url.rstrip("/")
    if path in ("", "/"):
        return [f"{base}/sse", base]
    if path == "/sse":
        return [server_url]
    return [server_url, f"{base}/sse"]


def _build_chat_tools(mcp_tools: list[dict], endpoint_url: str, transport: str = "streamable_http") -> list[ChatTool]:
    """Convert raw MCP tool dicts to ChatTool objects."""
    chat_tools = []
    for tool in mcp_tools:
        input_schema = tool.get("inputSchema", {})
        parameters = None
        if input_schema and input_schema.get("properties"):
            parameters = {
                "properties": input_schema.get("properties", {}),
                "required": input_schema.get("required", []),
            }

        chat_tool = ChatTool(
            name=tool["name"],
            description=tool.get("description", ""),
            endpoint=endpoint_url,
            method="POST",
            parameters=parameters,
            auth_required=False,
            status_message=f"Running {tool['name']}...",
            is_mcp=True,
            transport=transport,
        )
        chat_tools.append(chat_tool)
    return chat_tools


async def _initialize_session(server_url: str, access_token: Optional[str] = None) -> Optional[str]:
    """Establish an MCP session by sending initialize + notifications/initialized.

    Returns the session_id to use for subsequent requests.
    """
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
        pass  # Notifications may not return a response

    return session_id


async def call_mcp_tool(
    server_url: str,
    tool_name: str,
    arguments: dict,
    access_token: Optional[str] = None,
    oauth_tokens: Optional[dict] = None,
    transport: str = "streamable_http",
) -> str:
    """Call an MCP tool and return the text result.

    Supports both Streamable HTTP and SSE transports.
    If a 401 is received and oauth_tokens are available, attempts a token refresh and retries once.
    """
    if transport == "sse":
        return await _call_mcp_tool_sse(server_url, tool_name, arguments, access_token, oauth_tokens)

    return await _call_mcp_tool_http(server_url, tool_name, arguments, access_token, oauth_tokens)


async def _call_mcp_tool_http(
    server_url: str,
    tool_name: str,
    arguments: dict,
    access_token: Optional[str] = None,
    oauth_tokens: Optional[dict] = None,
) -> str:
    """Call an MCP tool via Streamable HTTP transport."""
    req = _jsonrpc_request(
        "tools/call",
        params={"name": tool_name, "arguments": arguments},
        req_id=3,
    )

    candidates = _resolve_mcp_url(server_url)
    last_error = None

    for url in candidates:
        try:
            session_id = await _initialize_session(url, access_token)
            resp, _ = await _mcp_post(url, req, access_token, session_id)
            break
        except PermissionError:
            if oauth_tokens and oauth_tokens.get("refresh_token"):
                new_tokens = await refresh_oauth_token(
                    oauth_tokens["token_endpoint"],
                    oauth_tokens["refresh_token"],
                    oauth_tokens["client_id"],
                    oauth_tokens.get("client_secret"),
                )
                oauth_tokens["access_token"] = new_tokens["access_token"]
                if new_tokens.get("refresh_token"):
                    oauth_tokens["refresh_token"] = new_tokens["refresh_token"]
                if new_tokens.get("expires_in"):
                    oauth_tokens["expires_at"] = time.time() + new_tokens["expires_in"]

                session_id = await _initialize_session(url, new_tokens["access_token"])
                resp, _ = await _mcp_post(url, req, new_tokens["access_token"], session_id)
                break
            else:
                return "Error: MCP server returned 401 Unauthorized and no refresh token available."
        except Exception as e:
            last_error = e
            continue
    else:
        if last_error:
            return f"Error calling MCP tool: {last_error}"
        return f"Error: Failed to connect to MCP server at {server_url}"

    return _extract_tool_result(resp)


async def _call_mcp_tool_sse(
    server_url: str,
    tool_name: str,
    arguments: dict,
    access_token: Optional[str] = None,
    oauth_tokens: Optional[dict] = None,
) -> str:
    """Call an MCP tool via SSE transport."""
    try:
        resp = await _call_tool_via_sse(server_url, tool_name, arguments, access_token)
    except PermissionError:
        if oauth_tokens and oauth_tokens.get("refresh_token"):
            new_tokens = await refresh_oauth_token(
                oauth_tokens["token_endpoint"],
                oauth_tokens["refresh_token"],
                oauth_tokens["client_id"],
                oauth_tokens.get("client_secret"),
            )
            oauth_tokens["access_token"] = new_tokens["access_token"]
            if new_tokens.get("refresh_token"):
                oauth_tokens["refresh_token"] = new_tokens["refresh_token"]
            if new_tokens.get("expires_in"):
                oauth_tokens["expires_at"] = time.time() + new_tokens["expires_in"]

            resp = await _call_tool_via_sse(server_url, tool_name, arguments, new_tokens["access_token"])
        else:
            return "Error: MCP server returned 401 Unauthorized and no refresh token available."
    except Exception as e:
        return f"Error calling MCP tool via SSE: {e}"

    return _extract_tool_result(resp)


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


# ---------------------------------------------------------------------------
# Brandfetch logo
# ---------------------------------------------------------------------------


def _extract_root_domain(domain: str) -> str:
    """Extract root domain from a full domain (e.g. mcp.notion.com -> notion.com)."""
    parts = domain.split(".")
    if len(parts) > 2:
        return ".".join(parts[-2:])
    return domain


async def fetch_brandfetch_logo(domain: str) -> Optional[str]:
    """Fetch a logo URL for a domain using Brandfetch CDN.

    Strips subdomains (e.g. mcp.notion.com -> notion.com) since logo services
    only have logos for root domains.
    Returns the logo CDN URL (which can be used as an image URL directly).
    """
    root_domain = _extract_root_domain(domain)
    return f"https://cdn.brandfetch.io/domain/{root_domain}?c=1idiDEee8WtzJbSEuuW"


def generate_state_token(app_id: str, uid: str) -> str:
    """Generate a state parameter for OAuth that encodes app_id and uid."""
    nonce = secrets.token_urlsafe(16)
    return f"{app_id}:{uid}:{nonce}"


def parse_state_token(state: str) -> tuple[str, str]:
    """Parse app_id and uid from an OAuth state parameter."""
    parts = state.split(":", 2)
    if len(parts) < 2:
        raise ValueError("Invalid state token")
    return parts[0], parts[1]
