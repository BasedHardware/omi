from fastapi import APIRouter
from fastapi import Request, HTTPException

from models import shared
from models import task
from utils.memories.process_memory import process_user_expression_measurement_callback
from utils.other import hume

router = APIRouter()


@router.post('/v1/agents/hume/callback', response_model=shared.EmptyResponse, tags=['agent', 'hume', 'callback'])
async def hume_expression_measurement_callback(request: Request, data: dict):
    job_callback = hume.HumeJobCallbackModel.from_dict("prosody", data)
    if job_callback is None:
        raise HTTPException(status_code=400, detail="Job callback is invalid")

    process_user_expression_measurement_callback(task.TaskActionProvider.HUME, job_callback.job_id, job_callback)

    # Empty response
    return {}
