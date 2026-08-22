from fastapi import APIRouter
from fastapi import Request, HTTPException

from models import shared
from models import task
from utils.conversations.process_conversation import process_user_expression_measurement_callback
from utils.other import hume
from utils.other.hume_callback_token import HumeCallbackTokenError, task_id_from_token

router = APIRouter()


@router.post('/v1/agents/hume/callback', response_model=shared.EmptyResponse, tags=['agent', 'hume', 'callback'])
def hume_expression_measurement_callback(request: Request, data: dict):
    # body untyped: external Hume AI webhook payload, forwarded wholesale to HumeJobCallbackModel.from_dict
    # which defensively parses an arbitrarily-nested prosody predictions structure. Modeling it would
    # duplicate Hume's API schema with no validation benefit since from_dict is the real parser.
    #
    # This route cannot carry a user token -- Hume calls it, and Hume has no user. Until the `t` parameter
    # existed, the job id in the BODY was the only thing tying a payload to a conversation, so anyone who
    # learned a job id could POST arbitrary prosody predictions and have them stored as somebody's
    # measured emotions (BACKLOG L42). `t` is signed by us when the job is submitted and names the Task
    # row that submission created; the handler then refuses a body whose job id resolves to a different
    # task. Refused BEFORE parsing the payload: an unauthenticated caller should not reach a parser.
    try:
        expected_task_id = task_id_from_token(request.query_params.get('t', ''))
    except HumeCallbackTokenError as error:
        # 401 with no detail: the reason a token was rejected (absent / forged / expired) is not
        # something an unauthenticated caller should be able to probe for.
        raise HTTPException(status_code=401, detail="Unauthorized") from error

    job_callback = hume.HumeJobCallbackModel.from_dict("prosody", data)
    if job_callback is None:
        raise HTTPException(status_code=400, detail="Job callback is invalid")

    process_user_expression_measurement_callback(
        task.TaskActionProvider.HUME, job_callback.job_id, job_callback, expected_task_id
    )

    # Empty response
    return {}
