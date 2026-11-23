"""One attributable WARNING line for every 503 the from-segments route returns.

The route's 503s come from its dependency chain as well as its handler, so the
hook wraps the whole route handler: FastAPI resolves dependencies inside it, so
an auth or rate-limit 503 is caught here too. The line carries the raise-site
tag and the serialized body length — never a user id, conversation id, title,
transcript or payload.

Every reachable 503 site tags its exception (``utils.other.raise_site``), so an
untagged 503 is a defect, not a normal outcome: it is logged at ERROR with a
distinct event so the health tick can alert on it instead of accepting it.

The route class keeps the external-list cache behaviour it already had; only
the from-segments path is instrumented.
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import HTTPException, Request
from fastapi.responses import Response

from utils.external_list_reads import ExternalListCacheRoute
from utils.other.raise_site import UNATTRIBUTED_RAISE_SITE, raise_site_of, serialized_detail_bytes

logger = logging.getLogger(__name__)

FROM_SEGMENTS_PATH = '/v1/conversations/from-segments'
FROM_SEGMENTS_503_EVENT = 'from_segments_503'
FROM_SEGMENTS_503_UNATTRIBUTED_EVENT = 'from_segments_503_unattributed'


def log_from_segments_503(*, raise_site: str, body_bytes: int, elapsed_ms: float) -> None:
    """Emit the single attribution line for one 503 on the route.

    A tagged site is the expected outcome and logs at WARNING. An untagged one
    is a defect in the enumeration and logs at ERROR under its own event, so it
    is alertable rather than silently accepted.
    """
    fields = {
        'event': FROM_SEGMENTS_503_EVENT,
        'route': FROM_SEGMENTS_PATH,
        'http_status': 503,
        'raise_site': raise_site,
        'body_bytes': body_bytes,
        'elapsed_ms': elapsed_ms,
    }
    if raise_site == UNATTRIBUTED_RAISE_SITE:
        fields['event'] = FROM_SEGMENTS_503_UNATTRIBUTED_EVENT
        logger.error('%s %s', FROM_SEGMENTS_503_UNATTRIBUTED_EVENT, json.dumps(fields, sort_keys=True), extra=fields)
        return
    logger.warning('%s %s', FROM_SEGMENTS_503_EVENT, json.dumps(fields, sort_keys=True), extra=fields)


class FromSegments503Route(ExternalListCacheRoute):
    """External-list cache route that names the raise site of a from-segments 503."""

    def get_route_handler(self):
        original = super().get_route_handler()
        if self.path != FROM_SEGMENTS_PATH:
            return original

        async def handler(request: Request) -> Response:
            started = time.monotonic()
            try:
                response = await original(request)
            except HTTPException as exc:
                if exc.status_code == 503:
                    log_from_segments_503(
                        raise_site=raise_site_of(exc),
                        body_bytes=serialized_detail_bytes(exc.detail),
                        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                    )
                raise
            if response.status_code == 503:
                # No reachable site returns a 503 response; a returned one has no
                # tag to read, so it is reported as the defect it is.
                log_from_segments_503(
                    raise_site=raise_site_of(None),
                    body_bytes=len(getattr(response, 'body', b'') or b''),
                    elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                )
            return response

        return handler
