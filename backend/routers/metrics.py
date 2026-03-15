import os

from fastapi import APIRouter, Header, HTTPException
from utils.metrics import metrics_response

router = APIRouter()


@router.get("/metrics")
def metrics(x_metrics_token: str = Header(default="")):
    expected = os.environ.get("METRICS_SECRET", "")
    if not expected or x_metrics_token != expected:
        raise HTTPException(status_code=403)
    return metrics_response()
