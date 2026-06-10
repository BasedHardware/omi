# backend/api/routes/health.py
from fastapi import APIRouter, Request
from typing import Dict, Any
import time
import logging
import os

from core.agent import agent_manager

logger = logging.getLogger(__name__)
router = APIRouter()

# Module-level variable to track start time
_start_time = time.time()

@router.get("/health")
async def health_check(request: Request) -> Dict[str, Any]:
    """
    Health check endpoint
    
    Returns system status, uptime, and MCP server status
    """
    current_time = time.time()
    uptime = current_time - _start_time
    
    return {
        "status": "healthy",
        "timestamp": current_time,
        "uptime_seconds": round(uptime, 2),
        "agent_initialized": agent_manager.is_initialized,
        "active_threads": agent_manager.get_active_thread_count(),
        "total_threads": agent_manager.get_thread_count(),
        "version": "1.0.0"
    }

@router.get("/status")
async def detailed_status() -> Dict[str, Any]:
    """
    Detailed status endpoint with more information
    """
    return {
        "agent": {
            "initialized": agent_manager.is_initialized,
            "llm_model": agent_manager.llm.model_name if agent_manager.llm else None,
        },
        "threads": {
            "active": agent_manager.get_active_thread_count(),
            "total": agent_manager.get_thread_count(),
        },
        "knowledge_base": {
            "enabled": bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY")),
            "upload_dir": os.getenv("UPLOAD_DIR", "./data/uploads"),
            "embedding_dim": int(os.getenv("EMBEDDING_DIM", "384"))
        }
    }