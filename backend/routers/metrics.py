from fastapi import APIRouter
from utils.metrics import metrics_response

router = APIRouter()


@router.get("/metrics")
def metrics():
    return metrics_response()
