# backend/api/routes/__init__.py
from fastapi import APIRouter
from api.routes import health, chat, knowledge

router = APIRouter()

router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])