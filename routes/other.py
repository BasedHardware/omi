from fastapi import APIRouter

router = APIRouter()


@router.get("/v1/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "ok"}
