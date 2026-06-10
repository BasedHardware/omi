
import logging
from typing import Dict, Any, List, Optional
from backend.orchestration.state import AgentState
import json
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph
from core.config import settings
from orchestration.state import AgentState  # Your state definition
logger = logging.getLogger(__name__)
from backend.orchestration.state import AgentState
import re

def global_memory_node(self, state: AgentState) -> AgentState:
        """Extract and update global memory"""
        try:
            llm = self.llm.get_cheap()
            
            extraction_prompt = f"""Extract key information to store in user memory.
            Only extract important facts: project names, team members, preferences, ongoing tasks.

            Query: {state['user_query']}
            Current memory: {state['global_memory'][:200]}...

            Output JSON: {{"important_entities": [], "context_to_store": ""}}
            If nothing important, return empty."""
            
            response = llm.invoke(extraction_prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Parse and update memory (integrate with your Supabase later)
            # For now, just log
            logger.info(f"Memory extraction for user {state['user_id']}")
            
        except Exception as e:
            logger.error(f"Global memory extraction failed: {e}")
            state["errors"].append(f"Memory extraction failed: {str(e)}")
        
        return state