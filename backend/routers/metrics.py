import hmac
import os

from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from utils.metrics import metrics_response

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


@router.get("/metrics")
def metrics(credentials: HTTPAuthorizationCredentials = Security(_bearer)):
    expected = (os.environ.get("METRICS_SECRET") or "").strip()
    token = credentials.credentials if credentials else ""
    if not expected or not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=401)
    return metrics_response()
