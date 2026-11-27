"""Pagination headers for ``GET /v1/conversations``; the list body keeps its shape.

``X-Omi-Conversation-Page-Size`` is the storage-row advance for the next
``offset``. Released apps (since #24541) already add it to their offset and
treat a value below the page size as the end, so a page cut short by a run of
hidden rows still advances past that run and keeps paging. It overrides the
membership projection's pre-suppression count, which was the same advance only
when no row was hidden. ``X-Omi-Has-More`` is ``false`` only at the end of the
query; ``X-Omi-Next-Cursor`` is set where the cursor lever is on.
"""

from typing import Any, Mapping

from utils.episodes import home_membership

HAS_MORE_HEADER = 'X-Omi-Has-More'
NEXT_CURSOR_HEADER = 'X-Omi-Next-Cursor'
HOME_MODE_HEADER = 'X-Omi-Home-Page-Mode'


def apply(response: Any, page: Mapping[str, Any]) -> None:
    """Copy a page collector's ``storage_rows``/``has_more``/``next_cursor`` onto the response."""
    if isinstance(page.get('storage_rows'), int):
        response.headers[home_membership.PAGE_SIZE_HEADER] = str(page['storage_rows'])
    if isinstance(page.get('has_more'), bool):
        response.headers[HAS_MORE_HEADER] = 'true' if page['has_more'] else 'false'
        if page['has_more'] and page.get('next_cursor'):
            response.headers[NEXT_CURSOR_HEADER] = page['next_cursor']
