import os

from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from utils.metrics import metrics_response

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


@router.get("/metrics")
def metrics(credentials: HTTPAuthorizationCredentials = Security(_bearer)):
    expected = os.environ.get("METRICS_SECRET", "")
    token = credentials.credentials if credentials else ""
    if not expected or token != expected:
        raise HTTPException(status_code=403)
    return metrics_response()
