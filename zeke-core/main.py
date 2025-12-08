from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import asyncio
import subprocess
import os
import uvicorn

from app.api import chat, memories, tasks, omi, sms, overland, curation, knowledge_graph, auth, context
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
_limitless_sync_task = None
_mcp_server_process = None
LIMITLESS_SYNC_INTERVAL = 90


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


def start_mcp_server():
    global _mcp_server_process
    try:
        mcp_venv_path = os.path.join(os.path.dirname(__file__), "..", "mcp", ".venv", "bin", "mcp-server-omi")
        if os.path.exists(mcp_venv_path):
            _mcp_server_process = subprocess.Popen(
                [mcp_venv_path, "-v"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "OMI_API_KEY": os.getenv("OMI_API_KEY", "")}
            )
            logger.info(f"Omi MCP Server started (PID: {_mcp_server_process.pid})")
        else:
            logger.warning(f"MCP server not found at {mcp_venv_path} - skipping MCP startup")
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")


def stop_mcp_server():
    global _mcp_server_process
    if _mcp_server_process:
        try:
            _mcp_server_process.terminate()
            _mcp_server_process.wait(timeout=5)
            logger.info("Omi MCP Server stopped")
        except subprocess.TimeoutExpired:
            _mcp_server_process.kill()
            logger.info("Omi MCP Server killed")
        except Exception as e:
            logger.error(f"Error stopping MCP server: {e}")
        _mcp_server_process = None


async def limitless_sync_loop():
    from app.integrations.limitless_bridge import LimitlessBridge
    from app.services.conversation_service import ConversationService
    
    await asyncio.sleep(10)
    
    while True:
        try:
            bridge = LimitlessBridge(
                conversation_service=ConversationService()
            )
            
            if bridge.is_enabled:
                synced_ids = await bridge.sync_recent(
                    user_id="default_user",
                    hours=1
                )
                if synced_ids:
                    logger.info(f"Limitless auto-sync: {len(synced_ids)} new conversations")
                else:
                    logger.debug("Limitless auto-sync: no new conversations")
            
        except Exception as e:
            logger.error(f"Limitless auto-sync error: {e}")
        
        await asyncio.sleep(LIMITLESS_SYNC_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _limitless_sync_task
    
    logger.info("Starting Zeke Core...")
    init_db()
    logger.info("Database initialized")
    await init_redis()
    register_event_handlers()
    
    start_mcp_server()
    
    _limitless_sync_task = asyncio.create_task(limitless_sync_loop())
    logger.info(f"Limitless auto-sync started (every {LIMITLESS_SYNC_INTERVAL}s)")
    
    yield
    
    if _limitless_sync_task:
        _limitless_sync_task.cancel()
        try:
            await _limitless_sync_task
        except asyncio.CancelledError:
            pass
        logger.info("Limitless auto-sync stopped")
    
    stop_mcp_server()
    
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
app.include_router(curation.router, prefix="/api")
app.include_router(knowledge_graph.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(context.router, prefix="/api")


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
