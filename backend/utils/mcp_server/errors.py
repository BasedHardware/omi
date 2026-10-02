"""Error types shared by hosted MCP handlers and transport."""

from typing import NoReturn, Optional

from fastapi import HTTPException
from google.api_core.exceptions import FailedPrecondition


class ToolExecutionError(Exception):
    """Exception raised when a tool execution fails.

    ``http_status`` records the originating HTTP status when the failure came
    from a REST-domain ``HTTPException``, so the REST routers can rethrow the
    exact status (409/422/404...) while the JSON-RPC tool surface still maps
    ``code`` to its stable ``isError`` schema.
    """

    def __init__(
        self,
        message: str,
        code: int = -32000,
        *,
        analytics_authorization_denied: bool = False,
        analytics_rate_limited: bool = False,
        http_status: Optional[int] = None,
    ):
        self.message = message
        self.code = code
        self.analytics_authorization_denied = analytics_authorization_denied
        self.analytics_rate_limited = analytics_rate_limited
        self.http_status = http_status
        super().__init__(self.message)


def authorization_denied_error(message: str) -> ToolExecutionError:
    """Preserve a product-authorization denial separately from its MCP code."""
    return ToolExecutionError(message, code=-32009, analytics_authorization_denied=True)


# Compatibility alias: older code/tests reference the private name.
_authorization_denied_error = authorization_denied_error


def tool_error_from_http(exc: HTTPException) -> ToolExecutionError:
    if exc.status_code == 404:
        return ToolExecutionError("Memory not found", code=-32001, http_status=404)
    if exc.status_code == 402:
        return ToolExecutionError("A paid plan is required to access this memory.", code=-32002, http_status=402)
    if exc.status_code == 403:
        denied = authorization_denied_error(str(exc.detail))
        denied.http_status = 403
        return denied
    if exc.status_code == 429:
        return ToolExecutionError(
            f"{exc.detail} Retry after the current rate-limit window.",
            code=-32009,
            analytics_rate_limited=True,
            http_status=429,
        )
    if exc.status_code in {409, 503}:
        return ToolExecutionError(str(exc.detail), code=-32009, http_status=exc.status_code)
    if exc.status_code >= 500:
        # A domain-code 5xx is a backend failure, never a client input problem;
        # keep the detail server-side rather than echoing limiter/store internals.
        return ToolExecutionError(
            "Tool temporarily unavailable. Retry shortly.", code=-32010, http_status=exc.status_code
        )
    return ToolExecutionError(str(exc.detail), http_status=exc.status_code)


def raise_tool_error_from_http(exc: HTTPException) -> NoReturn:
    raise tool_error_from_http(exc) from exc


_raise_tool_error_from_http = raise_tool_error_from_http


def raise_screen_activity_index_error(exc: FailedPrecondition) -> NoReturn:
    """Turn a missing-Firestore-index failure into a typed, actionable tool error.

    The app-filtered screen activity query needs a composite index (appName +
    timestamp). Without it Firestore raises FailedPrecondition, which otherwise
    surfaces to the MCP client as an opaque 500 (see AGENTS.md gotcha #7).
    """
    raise ToolExecutionError(
        "Screen activity isn't queryable right now — its search index is still being built. "
        "Retry in a few minutes, or narrow the request by removing the app filter.",
        code=-32009,
    ) from exc


def raise_conversation_index_error(exc: FailedPrecondition) -> NoReturn:
    raise ToolExecutionError(
        "Conversations aren't queryable right now because a search index is still being built. "
        "Retry in a few minutes.",
        code=-32009,
    ) from exc


def raise_action_item_index_error(exc: FailedPrecondition) -> NoReturn:
    raise ToolExecutionError(
        "Action items aren't queryable right now because a search index is still being built. "
        "Retry in a few minutes.",
        code=-32009,
    ) from exc


_raise_screen_activity_index_error = raise_screen_activity_index_error
_raise_conversation_index_error = raise_conversation_index_error
_raise_action_item_index_error = raise_action_item_index_error


def stable_error_code(exc: ToolExecutionError) -> str:
    """Map a tool failure to the stable snake_case code in ``structuredContent.error``."""
    if exc.analytics_authorization_denied:
        return "authorization_denied"
    if exc.analytics_rate_limited:
        return "rate_limited"
    return {
        -32001: "not_found",
        -32002: "paid_plan_required",
        -32602: "invalid_arguments",
        -32000: "invalid_arguments",
        -32003: "authorization_denied",
        -32009: "unavailable",
        -32010: "internal",
    }.get(exc.code, "internal")
