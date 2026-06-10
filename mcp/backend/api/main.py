# backend/main.py
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time

from api.routes import knowledge
from api.routes.auth import router as auth_router
from api.routes.chat import router as chat_router
from api.routes.knowledge import router as knowledge_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🚀 Starting Agentic Chatbot Backend...")
    
    # Set startup time in app state
    app.state.start_time = time.time()
    
    # # Create data directories if they don't exist
    # os.makedirs(os.getenv('FAISS_INDEX_DIR', './data/indices'), exist_ok=True)
    # os.makedirs(os.getenv('UPLOAD_DIR', './data/uploads'), exist_ok=True)
    # logger.info(f"📁 Upload directory: {os.getenv('UPLOAD_DIR', './data/uploads')}")
    
    # Import and initialize agent manager
    from core.agent import agent_manager
    
    try:
        # Step 1: Initialize AgentManager (MCP tools)
        await agent_manager.initialize()
        logger.info("✅ Agent initialized successfully")
               
    except Exception as e:
        logger.error(f"❌ Failed to initialize agent manager: {e}")
        logger.warning("⚠️  Continuing without agent - some features may not work")
    
    yield
    
    # Shutdown logic here
    logger.info("🛑 Shutting down backend...")
    try:
        await agent_manager.shutdown()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Create FastAPI app
app = FastAPI(
    title="Agentic Chatbot API",
    description="Backend API for the Agentic Chatbot",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration - MUST be before routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Import routes - AFTER app creation but BEFORE including them
try:
    from api.routes import health, chat, knowledge
    logger.info("✅ Routes imported successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import routes: {e}")
    logger.error("   Make sure api/routes/health.py, api/routes/chat.py, and api/routes/knowledge.py exist")
    raise

# Include routers with /api prefix
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth_router)
app.include_router(chat_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")

logger.info("✅ Routes registered:")
logger.info("   - /auth (all auth routes)")
logger.info("   - /api/health")
logger.info("   - /api/status")
logger.info("   - /api/thread")
logger.info("   - /api/thread/{thread_id}/chat")
logger.info("   - /api/knowledge/upload")
logger.info("   - /api/knowledge/resources")
logger.info("   - /api/knowledge/search")

# Root endpoint
@app.get("/")
async def root(request: Request):
    """Root endpoint"""
    start_time = getattr(request.app.state, 'start_time', time.time())
    uptime = time.time() - start_time
    return {
        "message": "Agentic Chatbot API",
        "status": "running",
        "version": "1.0.0",
        "uptime_seconds": round(uptime, 2),
        "endpoints": {
            "health": "/api/health",
            "status": "/api/status",
            "create_thread": "POST /api/thread",
            "chat": "POST /api/thread/{thread_id}/chat",
            "knowledge": {
                "upload": "POST /api/knowledge/upload",
                "resources": "GET /api/knowledge/resources",
                "search": "POST /api/knowledge/search"
            }
        }
    }

# Debug endpoint to list all routes
@app.get("/debug/routes")
async def list_routes():
    """List all registered routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods),
                "name": route.name
            })
    return {"routes": routes}

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Starting server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )