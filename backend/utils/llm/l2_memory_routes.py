"""Backward-compatible shim — implementation lives in ``utils.llm.promotion_routes`` (WS-G11)."""

from utils.llm.promotion_routes import (
    CLIENT_IMPORT_ERROR,
    L2MemoryRouteResponse,
    PromotionRouteResponse,
    QUOTE_WRAPPER_RE,
    canonical_json,
    classify_l2_memory_route,
    content_from_response,
    get_llm,
    is_quote_wrapper,
    l2_memory_route_prompt,
    logger,
    promotion_route_prompt,
)

_CLIENT_IMPORT_ERROR = CLIENT_IMPORT_ERROR
_QUOTE_WRAPPER_RE = QUOTE_WRAPPER_RE
_canonical_json = canonical_json
_content_from_response = content_from_response
_is_quote_wrapper = is_quote_wrapper

__all__ = [
    "L2MemoryRouteResponse",
    "PromotionRouteResponse",
    "_CLIENT_IMPORT_ERROR",
    "_QUOTE_WRAPPER_RE",
    "_canonical_json",
    "_content_from_response",
    "_is_quote_wrapper",
    "classify_l2_memory_route",
    "get_llm",
    "l2_memory_route_prompt",
    "logger",
    "promotion_route_prompt",
]
