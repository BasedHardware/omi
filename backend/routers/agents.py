from fastapi import APIRouter
from fastapi import Request, HTTPException

from models import shared
from models import task
from utils.conversations.process_conversation import process_user_expression_measurement_callback
from utils.other import hume

router = APIRouter()


@router.post('/v1/agents/hume/callback', response_model=shared.EmptyResponse, tags=['agent', 'hume', 'callback'])
def hume_expression_measurement_callback(request: Request, data: dict):
    # body untyped: external Hume AI webhook payload, forwarded wholesale to HumeJobCallbackModel.from_dict
    # which defensively parses an arbitrarily-nested prosody predictions structure. Modeling it would
    # duplicate Hume's API schema with no validation benefit since from_dict is the real parser.
    job_callback = hume.HumeJobCallbackModel.from_dict("prosody", data)
    # from_dict returns a model even for an empty payload — job_id is None on
    # a missing/empty job_id, and processing a null job-id crashes downstream.
    if job_callback is None or not job_callback.job_id:
        raise HTTPException(status_code=400, detail="Job callback is invalid")

    process_user_expression_measurement_callback(task.TaskActionProvider.HUME, job_callback.job_id, job_callback)

    # Empty response
    return {}
