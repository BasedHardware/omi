"""Memory product router.

This module defines the FastAPI routes that expose memory‑based product
search functionality.  The original implementation leaked internal
exception details (e.g. user IDs, document IDs) in HTTP 400 responses.
The routes now sanitize error messages to avoid exposing such internal
state while still logging the exception type for observability.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any

# Import the service and its dependency injector.
# The concrete implementation lives in `backend.services.memory_service`.
from backend.services.memory_service import (
    MemoryService,
    get_memory_service,
)

router = APIRouter()
log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper
# --------------------------------------------------------------------------- #
def _sanitize_value_error(exc: ValueError) -> HTTPException:
    """
    Convert a raw ``ValueError`` raised by the service layer into a generic
    ``HTTPException`` with a sanitized message.

    The function also logs a warning containing only the exception *type*
    (not the message) to keep internal details out of logs that might be
    exposed to end‑users.
    """
    log.warning(f"Memory product request rejected: {type(exc).__name__}")
    # The client only needs to know that the request was malformed.
    return HTTPException(
        status_code=400,
        detail="Invalid request parameters",
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get(
    "/search_product",
    summary="Search a product in memory",
    response_model=Any,  # The concrete schema is defined by the service.
)
async def search_product_memory(
    uid: str = Query(..., description="User identifier"),
    query: str = Query(..., description="Search query string"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    service: MemoryService = Depends(get_memory_service),
):
    """
    Search for a product in the user's memory store.

    Errors raised by the underlying service (e.g. UID mismatches) are
    sanitized before being sent to the client.
    """
    try:
        return await service.search_product(uid=uid, query=query, limit=limit)
    except ValueError as exc:
        raise _sanitize_value_error(exc) from None


@router.get(
    "/search_vector",
    summary="Search a vector in memory",
    response_model=Any,
)
async def search_vector_memory(
    uid: str = Query(..., description="User identifier"),
    vector_id: str = Query(..., description="Vector identifier"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    service: MemoryService = Depends(get_memory_service),
):
    """
    Search for a vector in the user's memory store.

    Any ``ValueError`` from the service layer is sanitized.
    """
    try:
        return await service.search_vector(uid=uid, vector_id=vector_id, limit=limit)
    except ValueError as exc:
        raise _sanitize_value_error(exc) from None


@router.get(
    "/search_archive",
    summary="Search an archived item in memory",
    response_model=Any,
)
async def search_archive_memory(
    uid: str = Query(..., description="User identifier"),
    archive_id: str = Query(..., description="Archive identifier"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    service: MemoryService = Depends(get_memory_service),
):
    """
    Search for an archived item in the user's memory store.

    Sanitizes ``ValueError`` to avoid leaking internal identifiers.
    """
    try:
        return await service.search_archive(uid=uid, archive_id=archive_id, limit=limit)
    except ValueError as exc:
        raise _sanitize_value_error(exc) from None
