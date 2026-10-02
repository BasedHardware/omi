"""Webhook and integration endpoints for background agent providers."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from models import shared, task
from utils.conversations.process_conversation import process_user_expression_measurement_callback
from utils.log_sanitizer import sanitize
from utils.other import hume

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/v1/agents/hume/callback', response_model=shared.EmptyResponse, tags=['agent', 'hume', 'callback'])
def hume_expression_measurement_callback(request: Request, data: Dict[str, Any]):
    # body untyped: external Hume AI webhook payload, forwarded wholesale to HumeJobCallbackModel.from_dict
    # which defensively parses an arbitrarily-nested prosody predictions structure. Modeling it would
    # duplicate Hume's API schema with no validation benefit since from_dict is the real parser.
    del request

    if not isinstance(data, dict) or not data:
        raise HTTPException(status_code=400, detail="Job callback is invalid")

    try:
        job_callback = hume.HumeJobCallbackModel.from_dict("prosody", data)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Failed to parse Hume job callback payload: %s", sanitize(exc))
        raise HTTPException(status_code=400, detail="Job callback is invalid") from exc

    if job_callback is None:
        raise HTTPException(status_code=400, detail="Job callback is invalid")

    raw_job_id = job_callback.job_id
    clean_job_id = raw_job_id.strip() if isinstance(raw_job_id, str) else ""
    if not clean_job_id:
        raise HTTPException(status_code=400, detail="Job ID is required")

    try:
        process_user_expression_measurement_callback(task.TaskActionProvider.HUME, clean_job_id, job_callback)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Failed to process Hume expression measurement callback for job {clean_job_id}: {sanitize(exc)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to process callback") from exc

    # Empty response
    return {}
