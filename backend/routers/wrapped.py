from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from ..utils.wrapped.error_sanitizer import sanitize_error
from ..models import WrappedStatus  # hypothetical ORM model
from ..db import get_db_session
from ..utils.wrapped.generate_2025 import generate_wrapped_2025

router = APIRouter(prefix="/v1/wrapped", tags=["wrapped"])


class WrappedRequest(BaseModel):
    # Define the expected payload for generation; fields are illustrative.
    data: dict[str, str]


@router.post("/{year}")
async def start_wrapped_generation(
    year: int,
    req: WrappedRequest,
    db = Depends(get_db_session),
):
    """
    Kick‑off background generation for a given year.
    """
    # Insert a placeholder status row if it does not exist.
    async with db as session:
        existing = await session.get(WrappedStatus, {"year": year})
        if not existing:
            session.add(WrappedStatus(year=year, status="queued", error=None))
            await session.commit()

    # Fire‑and‑forget the background job.
    generate_wrapped_2025(year, req.dict())
    return {"message": f"Wrapped generation for {year} queued."}


@router.get("/{year}")
async def get_wrapped_status(
    year: int,
    db = Depends(get_db_session),
):
    """
    Retrieve the current status of Wrapped‑2025 generation.
    The `error` field is always sanitised before being sent to the client.
    """
    async with db as session:
        record = await session.get(WrappedStatus, {"year": year})
        if not record:
            raise HTTPException(status_code=404, detail="Year not found")

        # Ensure any legacy raw error strings are masked.
        safe_error: Optional[str] = None
        if record.error:
            # If the stored error looks like a raw traceback (contains newlines
            # or the word "Traceback") we replace it with a generic message.
            if "\n" in record.error or "Traceback" in record.error:
                safe_error = "Internal server error"
            else:
                # Otherwise we run it through the same sanitizer used by the
                # background job – this also normalises formatting.
                safe_error = sanitize_error(RuntimeError(record.error))

        return {
            "year": year,
            "status": record.status,
            "error": safe_error,
        }
