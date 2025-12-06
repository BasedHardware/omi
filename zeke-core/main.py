from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import uvicorn

from app.api import chat, memories, tasks, omi, sms, overland
from app.core.config import get_settings
from app.core.database import init_db
from app.core.events import event_bus, Event, EventTypes
from app.core.redis import get_redis_pool, close_redis_pool, enqueue_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()

_redis_available = False


async def process_conversation_inline(conversation_id: str, user_id: str):
    from app.services.memory_service import MemoryService
    from app.services.conversation_service import ConversationService
    
    conversation_service = ConversationService()
    memory_service = MemoryService()
    
    conversation = await conversation_service.get_by_id(conversation_id)
    if not conversation or not conversation.overview:
        return 0
    
    transcript = conversation_service.get_transcript_text(conversation)
    
    memories = await memory_service.extract_from_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        transcript=transcript,
        overview=conversation.overview
    )
    
    return len(memories)


async def handle_conversation_created(event: Event):
    global _redis_available
    
    try:
        conversation_id = event.data.get("conversation_id")
        user_id = event.data.get("user_id")
        
        if not conversation_id or not user_id:
            return
        
        if _redis_available:
            try:
                await enqueue_job("process_conversation", conversation_id, user_id)
                logger.info(f"Queued conversation {conversation_id} for background processing")
                return
            except Exception as redis_error:
                logger.warning(f"Redis enqueue failed ({redis_error}), falling back to inline processing")
                _redis_available = False
        
        memories_count = await process_conversation_inline(conversation_id, user_id)
        logger.info(f"Extracted {memories_count} memories from conversation {conversation_id} (inline)")
        
    except Exception as e:
        logger.error(f"Error handling conversation.created event: {e}")


def register_event_handlers():
    event_bus.subscribe_async(EventTypes.CONVERSATION_CREATED, handle_conversation_created)
    logger.info("Event handlers registered")


async def init_redis():
    global _redis_available
    try:
        pool = await get_redis_pool()
        await pool.ping()
        _redis_available = True
        logger.info("Redis connected - background jobs enabled")
    except Exception as e:
        _redis_available = False
        logger.warning(f"Redis not available ({e}) - using in-process handling")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Zeke Core...")
    init_db()
    logger.info("Database initialized")
    await init_redis()
    register_event_handlers()
    yield
    await close_redis_pool()
    logger.info("Shutting down Zeke Core...")


app = FastAPI(
    title="Zeke Core",
    description="Personal AI Assistant API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(memories.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(omi.router, prefix="/api")
app.include_router(sms.router, prefix="/api")
app.include_router(overland.router, prefix="/api")


@app.get("/")
async def root():
    return {
        "name": "Zeke Core",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
