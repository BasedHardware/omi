from typing import Any, Dict, Optional, cast

from fastapi import APIRouter
from fastapi import Request, HTTPException

from models import shared
from models import task
from utils.conversations.process_conversation import process_user_expression_measurement_callback
from utils.other import hume

router = APIRouter()


@router.post('/v1/agents/hume/callback', response_model=shared.EmptyResponse, tags=['agent', 'hume', 'callback'])
def hume_expression_measurement_callback(request: Request, data: Dict[str, Any]) -> Dict[str, Any]:
    job_callback = cast(
        Optional[hume.HumeJobCallbackModel],
        hume.HumeJobCallbackModel.from_dict("prosody", data),  # type: ignore[reportUnknownMemberType]  # utils.other.hume.from_dict takes an untyped dict
    )
    if job_callback is None:
        raise HTTPException(status_code=400, detail="Job callback is invalid")

    process_user_expression_measurement_callback(
        task.TaskActionProvider.HUME,
        cast(str, job_callback.job_id),  # type: ignore[reportUnknownMemberType]  # utils.other.hume.HumeJobCallbackModel.job_id is untyped
        job_callback,
    )

    # Empty response
    return {}
