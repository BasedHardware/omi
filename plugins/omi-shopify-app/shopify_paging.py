"""Bounded since_id pagination for Shopify REST list endpoints.

Shopify's REST Admin API returns at most 250 records per page. Callers that
treat a single page as the full collection silently drop the rest of the catalog.
This helper follows the same since_id loop already used for analytics orders.
"""
from typing import Any, Callable, Dict, List, Optional

SHOPIFY_PAGE_SIZE = 250
SHOPIFY_MAX_PAGES = 10

RequestFn = Callable[..., Dict[str, Any]]


def fetch_all_pages(
    request_fn: RequestFn,
    uid: str,
    endpoint: str,
    resource_key: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    max_pages: int = SHOPIFY_MAX_PAGES,
    page_size: int = SHOPIFY_PAGE_SIZE,
) -> Dict[str, Any]:
    """GET a list endpoint until a short page, an error, or max_pages.

    Returns a dict with `resource_key` (the concatenated records). On the first
    page, a request error is returned as-is so callers keep their existing
    fallback. Later-page errors keep records already collected and set `error` plus
    `partial`. When the page cap is hit on a full last page, `capped` is True.
    """
    page_params: Dict[str, Any] = dict(params or {})
    page_params["limit"] = page_size
    items: List[Any] = []
    page_count = 0
    last_id = None
    capped = False

    while page_count < max_pages:
        this_params = dict(page_params)
        if last_id is not None:
            this_params["since_id"] = last_id
        result = request_fn(uid, "GET", endpoint, params=this_params)
        if "error" in result:
            if page_count == 0:
                return result
            print(
                f"⚠️ {endpoint} page {page_count + 1} error after {len(items)} "
                f"{resource_key}: {result['error']}"
            )
            return {
                resource_key: items,
                "page_count": page_count,
                "partial": True,
                "capped": False,
                "error": result["error"],
            }
        page_items = result.get(resource_key) or []
        items.extend(page_items)
        page_count += 1
        if len(page_items) < page_size:
            break
        last_id = page_items[-1].get("id") if page_items else None
        if last_id is None:
            break
    else:
        capped = True
        print(
            f"⚠️ {endpoint} pagination cap reached "
            f"({max_pages} pages, {len(items)} {resource_key})"
        )

    return {
        resource_key: items,
        "page_count": page_count,
        "partial": False,
        "capped": capped,
    }
