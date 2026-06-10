import asyncio
import uuid
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional, Any
from pathlib import Path
import time
import logging
from core.config import settings
from api.models.response import ChatChunk, ToolInfo
from orchestration.wow_orchestration import SmartOrchestrator
logger = logging.getLogger(__name__)


class AgentManager:
    """
    Manages conversation threads and routes all queries to SmartOrchestrator.
    
    The orchestrator handles ALL processing including:
    - LLM interactions
    - MCP server connections
    - Tool usage
    - Context gathering (web, RAG, club)
    - Multi-worker execution (GitHub, Google Workspace)
    """
    
    def __init__(self):
        # Smart Orchestrator (handles everything)
        self.orchestrator: Optional[SmartOrchestrator] = None
        
        # Thread management attributes
        self.threads: Dict[str, dict] = {}
        self.active_threads: set = set()
        
        # Initialization flag
        self._initialized: bool = False
        
        logger.info("AgentManager instance created")
    
    async def initialize(self):
        """
        Initialize the Smart Orchestrator.
        
        The orchestrator handles all MCP servers, tools, and LLM connections internally.
        """
        if self._initialized:
            logger.warning("Agent already initialized")
            return
        
        logger.info("🚀 Initializing Agent Manager with Smart Orchestrator...")
        
        try:
            # Initialize Smart Orchestrator (it handles everything internally)
            self.orchestrator = SmartOrchestrator()
            logger.info("✅ Smart Orchestrator initialized successfully")
            logger.info("   The orchestrator will handle:")
            logger.info("   • LLM (Groq)")
            logger.info("   • Context providers (Web, RAG, Club)")
            logger.info("   • Workers (GitHub, Google Workspace, Conversational)")
            logger.info("   • MCP servers (as configured in orchestrator)")
            
            self._initialized = True
            logger.info("🎉 Agent Manager initialization complete!\n")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Smart Orchestrator: {e}")
            logger.error("   Please ensure:")
            logger.error("   1. smart_orchestrator.py is in the correct location")
            logger.error("   2. All dependencies are installed")
            logger.error("   3. Required environment variables are set (GROQ_API_KEY, etc.)")
            raise RuntimeError(f"Cannot start without Smart Orchestrator: {e}")
    
    async def shutdown(self):
        """Gracefully shutdown agent"""
        logger.info("🛑 Shutting down Agent Manager...")
        if self.orchestrator:
            await self.orchestrator.cleanup()
        self._initialized = False
        logger.info("✅ Agent Manager shutdown complete")
    
    # ========== THREAD MANAGEMENT METHODS ==========
    
    def create_thread(self, user_id: str = "") -> str:
        thread_id = str(uuid.uuid4())
        self.threads[thread_id] = {           # ✅ self.threads
            "created_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "messages": [],
            "status": "active",
        }
        logger.info(f"Created thread {thread_id} for user {user_id or '(anonymous)'}")
        return thread_id

    def get_thread(self, thread_id: str) -> Optional[dict]:
        return self.threads.get(thread_id)    # ✅ self.threads

    def delete_thread(self, thread_id: str, user_id: str = "") -> bool:
        thread = self.threads.get(thread_id)  # ✅ self.threads
        if thread is None:
            return False
        if user_id and thread.get("user_id") and thread["user_id"] != user_id:
            logger.warning(f"User {user_id} tried to delete thread {thread_id} owned by {thread['user_id']}")
            return False
        del self.threads[thread_id]           # ✅ self.threads
        return True

    def get_messages(self, thread_id: str, user_id: str = "") -> Optional[List[Dict]]:
        thread = self.threads.get(thread_id)  # ✅ self.threads
        if thread is None:
            return None
        if user_id and thread.get("user_id") and thread["user_id"] != user_id:
            logger.warning(f"User {user_id} tried to read thread {thread_id} owned by {thread['user_id']}")
            return None
        return thread.get("messages", [])

    def list_threads(self) -> List[dict]:
        return [
            {
                "id": tid,
                "created_at": t["created_at"],
                "message_count": len(t["messages"]),
                "status": t.get("status", "active"),
            }
            for tid, t in self.threads.items()
        ]

    def add_message(self, thread_id: str, role: str, content: str, metadata: Optional[dict] = None) -> bool:
        thread = self.threads.get(thread_id)
        if not thread:
            return False
        thread["messages"].append({
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        })
        return True

    def clear_thread(self, thread_id: str) -> bool:
        thread = self.threads.get(thread_id)
        if not thread:
            return False
        thread["messages"] = []
        return True

    def get_thread_count(self) -> int:
        return len(self.threads)

    def get_active_thread_count(self) -> int:
        return len(self.active_threads)
    
    # ========== ORCHESTRATOR-BASED CHAT METHODS ==========
    
    async def chat(
        self,
        message: str,
        thread_id: Optional[str] = None,
        user_id: str = "",
        conversation_history: Optional[List[str]] = None,   # ← NEW (pre-built by chat.py)
    ) -> Dict[str, Any]:
        """
        Process a message through the orchestrator.

        conversation_history — when provided by the caller (chat.py), it is used
        directly instead of rebuilding from self.threads. This keeps agent.py
        stateless with respect to memory; all persistence lives in session_memory.py.
        """
        if not self.is_initialized:
            raise RuntimeError("Agent not initialized")

        # Ensure in-memory thread entry exists (lightweight fallback)
        if thread_id not in self.threads:
            self.threads[thread_id] = {
                "created_at": datetime.utcnow().isoformat(),
                "user_id": user_id,
                "messages": [],
                "status": "active",
            }

        start = datetime.utcnow()

        # Use caller-supplied history; fall back to in-memory last 10 if absent
        if conversation_history is None:
            conversation_history = [
                f"{m['role']}: {m['content']}"
                for m in self.threads[thread_id].get("messages", [])[-10:]
            ]

        result = await self.orchestrator.process(
            user_query=message,
            conversation_history=conversation_history,
            user_id=user_id,
        )

        elapsed = (datetime.utcnow() - start).total_seconds()
        message_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        if result.get("interrupted"):
            self.threads[thread_id]["messages"].append(
                {"id": str(uuid.uuid4()), "role": "user", "content": message, "timestamp": now}
            )
            return {
                "interrupted": True,
                "confirmation_required": result["confirmation_required"],
                "thread_id": thread_id,
                "message_id": message_id,
                "execution_time": elapsed,
            }

        response_text = result.get("response", "Sorry, I could not process that.")

        self.threads[thread_id]["messages"].extend([
            {"id": str(uuid.uuid4()), "role": "user",      "content": message,       "timestamp": now},
            {"id": message_id,        "role": "assistant", "content": response_text, "timestamp": now},
        ])

        return {
            "interrupted": False,
            "message": response_text,
            "thread_id": thread_id,
            "message_id": message_id,
            "execution_time": elapsed,
        }
    
    async def resume(
        self,
        thread_id: str,
        user_response: str,
        user_id: str = "",
    ) -> Dict[str, Any]:
        """
        Resume a paused graph after the user approves or rejects a HITL confirmation.

        Args:
            thread_id:     Thread ID from the interrupted response.
            user_response: "approve" or "reject".
            user_id:       Supabase user UUID (for token lookups).

        Returns the same shape as chat() — either a final response or another interruption.
        """
        if not self.is_initialized:
            raise RuntimeError("Agent not initialized")

        start = datetime.utcnow()
        message_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        result = await self.orchestrator.resume(
            user_id=thread_id,       # orchestrator keys pending by user_id
            user_response=user_response,
        )

        elapsed = (datetime.utcnow() - start).total_seconds()

        # Another HITL pause (multiple write tasks)
        if result.get("interrupted"):
            return {
                "interrupted": True,
                "confirmation_required": result["confirmation_required"],
                "thread_id": thread_id,
                "message_id": message_id,
                "execution_time": elapsed,
            }

        response_text = result.get("response", "Action completed.")

        # Add assistant response to thread history
        if thread_id in self.threads:
            self.threads[thread_id]["messages"].append(
                {"id": message_id, "role": "assistant", "content": response_text, "timestamp": now}
            )

        return {
            "interrupted": False,
            "message": response_text,
            "thread_id": thread_id,
            "message_id": message_id,
            "execution_time": elapsed,
        }

    async def stream_chat(
        self,
        message: str,
        thread_id: Optional[str] = None,
        user_id: str = "",
    ) -> AsyncGenerator[ChatChunk, None]:
        if not self._initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        if not thread_id:
            thread_id = self.create_thread(user_id=user_id)

        logger.warning("⚠️  Orchestrator streaming not yet implemented — faking it")

        try:
            result = await self.chat(message, thread_id, user_id=user_id)
            words = result["message"].split()
            for i, word in enumerate(words):
                yield ChatChunk(
                    type="token",
                    content=word + (" " if i < len(words) - 1 else ""),
                    metadata={"thread_id": thread_id},
                )
                await asyncio.sleep(0.01)

            yield ChatChunk(
                type="done",
                metadata={"thread_id": thread_id, **result.get("metadata", {})},
            )
        except Exception as e:
            logger.error(f"❌ Error during streaming: {e}")
            yield ChatChunk(type="error", content=str(e), metadata={"thread_id": thread_id})
    
    # ========== STATUS AND INFO METHODS ==========
    
    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get status of Smart Orchestrator"""
        if not self.orchestrator:
            return {
                "enabled": False,
                "status": "not_initialized",
                "message": "Orchestrator not initialized"
            }
        
        return {
            "enabled": True,
            "status": "ready",
            "features": {
                "web_search": True,
                "rag_search": True,
                "club_search": True,
                "github_worker": True,
                "google_workspace_worker": True,
                "conversational_worker": True,
                "mixed_context": True,
                "intelligent_planning": True
            },
            "description": "All queries are processed through Smart Orchestrator"
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall agent manager status"""
        return {
            "initialized": self._initialized,
            "orchestrator": self.get_orchestrator_status(),
            "threads": {
                "total": self.get_thread_count(),
                "active": self.get_active_thread_count()
            }
        }
    
    @property
    def is_initialized(self) -> bool:
        """Check if agent is ready to use"""
        return self._initialized and self.orchestrator is not None


# Global instance (singleton pattern)
agent_manager = AgentManager()