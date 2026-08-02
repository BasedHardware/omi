from fastapi import APIRouter, Depends

from models.memory_platform import MemoryPlatformCapability
from utils.memory.platform import build_memory_platform_capability
from utils.other import endpoints as auth

router = APIRouter()


@router.get(
    '/v1/memory/platform',
    tags=['v1', 'memory'],
    response_model=MemoryPlatformCapability,
)
def get_memory_platform(uid: str = Depends(auth.get_current_user_uid)) -> MemoryPlatformCapability:
    return build_memory_platform_capability()


__all__ = ['get_memory_platform', 'router']
