from fastapi import APIRouter
from fastapi import Request

router = APIRouter()

@router.get('/v1/health', tags=['v1'])
async def health_check(request: Request):
    return {'status': 'healthy'} # TODO: Add more health checks for the llm, database, etc.