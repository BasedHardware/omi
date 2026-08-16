from __future__ import annotations

import uuid

from fastapi import Request

REQUEST_ID_HEADER = 'x-omi-request-id'
REQUEST_ID_MAX_LENGTH = 64


def request_id_for(request: Request) -> str:
    request_id = getattr(request.state, 'request_id', None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return 'unknown'


def resolve_request_id(raw_request_id: str | None) -> str:
    """Accept only canonical UUID request IDs; generate an opaque ID otherwise."""
    if raw_request_id is not None:
        candidate = raw_request_id.strip()[:REQUEST_ID_MAX_LENGTH]
        try:
            parsed = uuid.UUID(candidate)
        except (ValueError, AttributeError):
            pass
        else:
            if str(parsed) == candidate.lower():
                return str(parsed)
    return str(uuid.uuid4())
