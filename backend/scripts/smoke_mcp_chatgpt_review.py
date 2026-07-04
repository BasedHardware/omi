#!/usr/bin/env python3
"""Run a redacted ChatGPT MCP reviewer smoke against a live Omi backend."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

BASE_URL = os.getenv("OMI_MCP_REVIEW_BASE_URL", "https://api.omi.me").rstrip("/")
CLIENT_ID = os.getenv("OMI_MCP_REVIEW_CLIENT_ID", "omi-chatgpt-prod")
RESOURCE = os.getenv("OMI_MCP_REVIEW_RESOURCE", f"{BASE_URL}/v1/mcp/sse")
STATIC_REDIRECT_URI = "https://chatgpt.com/connector_platform_oauth_redirect"
DYNAMIC_REDIRECT_URI = "https://chatgpt.com/connector/oauth/omi-review-smoke/callback"
FIREBASE_SIGNIN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
SCOPES = (
    "memories.read memories.write conversations.read action_items.read action_items.write "
    "goals.read chat.read screen_activity.read people.read"
)


@dataclass
class HttpResult:
    status: int
    body: str
    headers: dict[str, str]


class SmokeFailure(Exception):
    pass


def _request(
    method: str,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> HttpResult:
    payload = None
    request_headers = dict(headers or {})
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 live smoke fixed URLs
            body = response.read().decode("utf-8", errors="replace")
            return HttpResult(response.status, body, dict(response.headers))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(exc.code, body, dict(exc.headers))


def _form_request(url: str, form: dict[str, str]) -> HttpResult:
    payload = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 live smoke fixed URL
            body = response.read().decode("utf-8", errors="replace")
            return HttpResult(response.status, body, dict(response.headers))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(exc.code, body, dict(exc.headers))


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _authorize_url(redirect_uri: str, verifier: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "resource": RESOURCE,
            "scope": SCOPES,
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{BASE_URL}/authorize?{query}"


def _extract_firebase_api_key(authorize_html: str) -> str:
    env_key = os.getenv("OMI_MCP_REVIEW_FIREBASE_API_KEY", "").strip()
    if env_key:
        return env_key
    match = re.search(r'"apiKey"\s*:\s*"([^"]+)"', authorize_html)
    if not match:
        raise SmokeFailure("Could not find Firebase API key in authorize HTML")
    return html.unescape(match.group(1))


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SmokeFailure(f"{name} is required")
    return value


def _firebase_password_signin(api_key: str, email: str, password: str) -> str:
    response = _request(
        "POST",
        f"{FIREBASE_SIGNIN_URL}?{urllib.parse.urlencode({'key': api_key})}",
        data={"email": email, "password": password, "returnSecureToken": True},
    )
    if response.status != 200:
        raise SmokeFailure(f"Firebase password sign-in failed with HTTP {response.status}")
    payload = json.loads(response.body)
    id_token = payload.get("idToken")
    if not id_token:
        raise SmokeFailure("Firebase password sign-in did not return an ID token")
    return id_token


def _authorize_consent(redirect_uri: str, verifier: str, firebase_id_token: str, state: str) -> str:
    response = _form_request(
        f"{BASE_URL}/authorize",
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "resource": RESOURCE,
            "scope": SCOPES,
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "firebase_id_token": firebase_id_token,
        },
    )
    if response.status != 200:
        raise SmokeFailure(f"Authorize consent failed with HTTP {response.status}")
    payload = json.loads(response.body)
    redirect_with_code = payload.get("redirect_uri", "")
    parsed = urllib.parse.urlsplit(redirect_with_code)
    code = dict(urllib.parse.parse_qsl(parsed.query)).get("code")
    if not code:
        raise SmokeFailure("Authorize consent did not return an authorization code")
    return code


def _exchange_token(code: str, redirect_uri: str, verifier: str) -> str:
    response = _request(
        "POST",
        f"{BASE_URL}/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "resource": RESOURCE,
            "code": code,
            "code_verifier": verifier,
        },
    )
    if response.status != 200:
        raise SmokeFailure(f"Token exchange failed with HTTP {response.status}")
    payload = json.loads(response.body)
    access_token = payload.get("access_token")
    if not access_token:
        raise SmokeFailure("Token exchange did not return an access token")
    return access_token


def _mcp_call(access_token: str, method: str, params: dict[str, Any] | None = None, msg_id: int = 1) -> dict[str, Any]:
    response = _request(
        "POST",
        RESOURCE,
        data={"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}},
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    if response.status != 200:
        raise SmokeFailure(f"MCP {method} failed with HTTP {response.status}")
    return json.loads(response.body)


def _tool_call(access_token: str, name: str, arguments: dict[str, Any], msg_id: int) -> dict[str, Any]:
    return _mcp_call(access_token, "tools/call", {"name": name, "arguments": arguments}, msg_id=msg_id)


def _assert_jsonrpc_success(payload: dict[str, Any], label: str) -> None:
    if payload.get("error"):
        raise SmokeFailure(f"{label} returned JSON-RPC error code {payload['error'].get('code')}")
    if "result" not in payload:
        raise SmokeFailure(f"{label} did not return a JSON-RPC result")


def _head(value: str, max_len: int = 120) -> str:
    return value.replace("\n", " ")[:max_len]


def main() -> int:
    summary: dict[str, Any] = {}
    try:
        verifier = _pkce_verifier()
        static_authorize = _request("GET", _authorize_url(STATIC_REDIRECT_URI, verifier, "static-smoke"))
        summary["static_authorize_get"] = {
            "status": static_authorize.status,
            "has_password_input": "password" in static_authorize.body.lower(),
        }
        if static_authorize.status != 200:
            raise SmokeFailure(
                f"Static authorize returned HTTP {static_authorize.status}: {_head(static_authorize.body)}"
            )

        dynamic_authorize = _request("GET", _authorize_url(DYNAMIC_REDIRECT_URI, verifier, "dynamic-smoke"))
        summary["dynamic_authorize_get"] = {"status": dynamic_authorize.status}
        if dynamic_authorize.status != 200:
            raise SmokeFailure(
                f"Dynamic authorize returned HTTP {dynamic_authorize.status}: {_head(dynamic_authorize.body)}"
            )

        email = _require_env("OMI_MCP_REVIEW_EMAIL")
        password = _require_env("OMI_MCP_REVIEW_PASSWORD")
        firebase_api_key = _extract_firebase_api_key(static_authorize.body)
        firebase_id_token = _firebase_password_signin(firebase_api_key, email, password)
        summary["firebase_password_signin"] = {"status": 200, "ok": True}

        static_code = _authorize_consent(STATIC_REDIRECT_URI, verifier, firebase_id_token, "static-smoke")
        summary["static_authorize_post"] = {"status": 200, "code_returned": True}

        static_access_token = _exchange_token(static_code, STATIC_REDIRECT_URI, verifier)
        summary["static_token_exchange"] = {"status": 200, "access_token_returned": bool(static_access_token)}

        dynamic_verifier = _pkce_verifier()
        dynamic_code = _authorize_consent(
            DYNAMIC_REDIRECT_URI,
            dynamic_verifier,
            firebase_id_token,
            "dynamic-smoke",
        )
        summary["dynamic_authorize_post"] = {"status": 200, "code_returned": True}

        access_token = _exchange_token(dynamic_code, DYNAMIC_REDIRECT_URI, dynamic_verifier)
        summary["dynamic_token_exchange"] = {"status": 200, "access_token_returned": True}

        initialize = _mcp_call(access_token, "initialize", msg_id=1)
        _assert_jsonrpc_success(initialize, "initialize")
        summary["mcp_initialize"] = {"status": 200, "body_error": None}

        tools_list = _mcp_call(access_token, "tools/list", msg_id=2)
        _assert_jsonrpc_success(tools_list, "tools/list")
        tool_count = len(tools_list.get("result", {}).get("tools", []))
        summary["mcp_tools_list"] = {"status": 200, "tool_count": tool_count, "body_error": None}

        conversations = _tool_call(access_token, "get_conversations", {"limit": 1}, msg_id=3)
        _assert_jsonrpc_success(conversations, "get_conversations")
        summary["mcp_get_conversations_no_category"] = {"status": 200, "body_error": None}

        categorized_conversations = _tool_call(
            access_token,
            "get_conversations",
            {"limit": 1, "categories": ["other"]},
            msg_id=4,
        )
        _assert_jsonrpc_success(categorized_conversations, "get_conversations category filter")
        summary["mcp_get_conversations_with_category_other"] = {"status": 200, "body_error": None}
    except Exception as exc:
        summary["failure"] = str(exc)
        print(json.dumps(summary, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
