"""HTTP client for the local Omi Desktop tool API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

import httpx

from omi_cli.client import DEFAULT_TIMEOUT, USER_AGENT, _extract_detail, _safe_parse_json
from omi_cli.errors import CliError, ServerError, from_status

LOCAL_TOOL_PATH = "/v1/local/tool"
LOCAL_TOOLS_PATH = "/v1/local/tools"


class LocalOmiClient:
    """Small sync client for the Desktop-local tool bridge."""

    def __init__(
        self,
        *,
        api_url: str,
        token: str,
        timeout: Optional[httpx.Timeout] = None,
        verbose: bool = False,
    ) -> None:
        if not api_url:
            raise CliError(
                message="Local API URL is not configured",
                detail="Run `omi local configure --url URL --token TOKEN` or set OMI_LOCAL_API_URL.",
                exit_code=2,
            )
        if not token:
            raise CliError(
                message="Local API token is not configured",
                detail="Run `omi local configure --url URL --token TOKEN` or set OMI_LOCAL_TOKEN.",
                exit_code=2,
            )

        self._verbose = verbose
        self._http = httpx.Client(
            base_url=api_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
            timeout=timeout or DEFAULT_TIMEOUT,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LocalOmiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def call_tool(self, name: str, arguments: Optional[Mapping[str, Any]] = None) -> Any:
        """Call one Desktop-local tool through the local API endpoint."""
        body = {"name": name, "arguments": dict(arguments or {})}
        try:
            response = self._http.post(LOCAL_TOOL_PATH, json=body)
        except httpx.TransportError as exc:
            raise ServerError(
                message="Local Omi Desktop API is unreachable",
                detail=str(exc),
            ) from exc

        self._maybe_log(name, response)
        if not (200 <= response.status_code < 300):
            raise self._error_from_response(response)
        return _unwrap_tool_response(_safe_parse_json(response))

    def list_tools(self) -> Any:
        """Return Desktop-local tool descriptors."""
        try:
            response = self._http.get(LOCAL_TOOLS_PATH)
        except httpx.TransportError as exc:
            raise ServerError(
                message="Local Omi Desktop API is unreachable",
                detail=str(exc),
            ) from exc

        self._maybe_log("tools", response, method="GET", path=LOCAL_TOOLS_PATH)
        if not (200 <= response.status_code < 300):
            raise self._error_from_response(response)
        return _safe_parse_json(response)

    def _maybe_log(
        self,
        tool_name: str,
        response: httpx.Response,
        *,
        method: str = "POST",
        path: str = LOCAL_TOOL_PATH,
    ) -> None:
        if not self._verbose:
            return
        import sys

        sys.stderr.write(
            f"[debug] {method} {path} tool={tool_name} → {response.status_code} "
            f"({response.elapsed.total_seconds():.2f}s)\n"
        )

    def _error_from_response(self, response: httpx.Response) -> CliError:
        detail = _extract_detail(response)
        if 500 <= response.status_code < 600:
            return ServerError(message=f"Local Omi Desktop API error ({response.status_code})", detail=detail)
        return from_status(response.status_code, detail=detail)


def _unwrap_tool_response(body: Any) -> Any:
    """Normalize Desktop-local API responses to the actual command result."""
    if not isinstance(body, Mapping):
        return body

    error = body.get("error")
    if isinstance(error, Mapping):
        raw_message = error.get("message")
        message = raw_message if isinstance(raw_message, str) else "Local tool error"
        raise CliError(message=message, detail=json.dumps(error, sort_keys=True), exit_code=1)
    if error:
        raise CliError(message=str(error), exit_code=1)

    if body.get("ok") is False:
        message = "Local tool error"
        raise CliError(message=message, detail=json.dumps(body, sort_keys=True), exit_code=1)

    result = body["result"] if "result" in body else body
    return _unwrap_tool_result(result)


def _unwrap_tool_result(result: Any) -> Any:
    if isinstance(result, str):
        return _parse_embedded_json(result)
    if isinstance(result, Mapping):
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, Mapping) and first.get("type") == "text":
                text = first.get("text")
                if isinstance(text, str):
                    return _parse_embedded_json(text)
        if set(result.keys()) == {"content"}:
            return content
    return result


def _parse_embedded_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return text


def existing_path(value: str) -> Optional[Path]:
    """Return Path(value) only when value points to an existing file."""
    try:
        path = Path(value).expanduser()
    except RuntimeError:
        return None
    return path if path.is_file() else None
