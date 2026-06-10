import logging
from typing import Dict, Any, List, Optional
from backend.orchestration.state import AgentState
import json
import re
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph
from core.config import settings
from orchestration.state import AgentState  # Your state definition
logger = logging.getLogger(__name__)

def red_flag_node(self, state: AgentState) -> AgentState:
        """Detect unethical/destructive queries"""
        query = state["user_query"].lower()
        
        # Regex patterns for obvious red flags
        destructive_patterns = [
            r'\bdelete\s+(all|everything|files?|repos?|emails?)\b',
            r'\bremove\s+(all|everything)\b',
            r'\bdestroy\b',
            r'\bwipe\s+out\b',
        ]
        
        unethical_keywords = [
            'hack', 'exploit', 'bypass security', 'cheat', 'plagiarize',
            'steal', 'illegal'
        ]
        
        # Quick regex check
        for pattern in destructive_patterns:
            if re.search(pattern, query):
                state["red_flag"] = True
                state["final_response"] = self._get_fallback_response()
                logger.warning(f"Red flag detected (regex): {query[:50]}")
                return state
        
        # Check unethical keywords with LLM for context
        for keyword in unethical_keywords:
            if keyword in query:
                try:
                    llm = self.llm.get_cheap()
                    prompt = f"""Is this query requesting something unethical or harmful?
Query: {state['user_query']}

Answer with just "YES" or "NO" and brief reason."""
                    
                    response = llm.invoke(prompt)
                    content = response.content if hasattr(response, 'content') else str(response)
                    
                    if "YES" in content.upper():
                        state["red_flag"] = True
                        state["final_response"] = self._get_fallback_response()
                        logger.warning(f"Red flag detected (LLM): {query[:50]}")
                        return state
                except Exception as e:
                    logger.error(f"LLM red flag check failed: {e}")
                break
        
        state["red_flag"] = False
        return state