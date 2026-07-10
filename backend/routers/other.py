from fastapi import APIRouter

from models.shared import StatusResponse

router = APIRouter()


@router.api_route("/v1/health", methods=["GET", "HEAD"], response_model=StatusResponse)
def health_check():
    """
    Health check endpoint.
    """
    return {"status": "ok"}
