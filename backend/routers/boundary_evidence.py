"""Authenticated, idempotent capture boundary evidence intake."""

from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Body

from models.boundary_evidence import BoundarySignal
from utils.episodes import boundary_store
from utils.episodes.boundaries import boundary_roster as boundary_roster
from utils.executors import db_executor, run_blocking
from utils.other.endpoints import get_current_user_uid, with_rate_limit

router = APIRouter()


@router.post('/v1/capture/boundary-evidence', tags=['capture'])
async def store_boundary_evidence(
    signals: Annotated[list[BoundarySignal], Body(max_length=64)],
    uid: str = Depends(with_rate_limit(get_current_user_uid, 'episodes:write')),
) -> dict[str, int]:
    if sum(len(signal.model_dump_json().encode('utf-8')) for signal in signals) > 262144:
        raise HTTPException(status_code=413, detail='Boundary evidence payload too large')
    for signal in signals:
        # Normalize naive timestamps at the wire boundary; comparisons are UTC.
        signal.started_at = (
            signal.started_at.replace(tzinfo=timezone.utc) if signal.started_at.tzinfo is None else signal.started_at
        )
        if signal.ended_at is not None:
            signal.ended_at = (
                signal.ended_at.replace(tzinfo=timezone.utc) if signal.ended_at.tzinfo is None else signal.ended_at
            )
            if signal.ended_at < signal.started_at:
                raise HTTPException(status_code=422, detail='Boundary end precedes start')
    try:
        stored = await run_blocking(db_executor, boundary_store.record, uid, signals)
    except boundary_store.BoundaryCapacityError:
        raise HTTPException(status_code=409, detail='Boundary evidence capacity reached')
    except ValueError:
        raise HTTPException(status_code=409, detail='Boundary evidence identity conflict')
    from utils.episodes.boundary_runtime import apply_signal_edges

    await run_blocking(db_executor, apply_signal_edges, uid)
    return {'stored': stored}
