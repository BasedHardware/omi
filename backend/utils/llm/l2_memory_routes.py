"""Backward-compatible shim — implementation lives in ``utils.llm.promotion_routes`` (WS-G11)."""

from utils.llm.promotion_routes import (
    L2MemoryRouteResponse,
    PromotionRouteResponse,
    _CLIENT_IMPORT_ERROR,
    _QUOTE_WRAPPER_RE,
    _canonical_json,
    _content_from_response,
    _is_quote_wrapper,
    classify_l2_memory_route,
    get_llm,
    l2_memory_route_prompt,
    logger,
    promotion_route_prompt,
)

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
