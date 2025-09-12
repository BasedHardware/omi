from fastapi import APIRouter

router = APIRouter()


@router.api_route("/v1/health", methods=["GET", "HEAD"])
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "ok"}
