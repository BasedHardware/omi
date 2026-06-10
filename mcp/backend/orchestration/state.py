
import os
import json
from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator



# ============================================================================
# STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    """State passed between nodes in the graph"""
    # Input
    user_query: str
    conversation_history: List[Dict[str, str]]
    global_memory: str
    user_id: str
    session_id: str
    
    # Flags and routing
    red_flag: bool
    intent_categories: List[str]            # Only planning_node writes this
    tools_used: Annotated[List[str], operator.add]  # Combines lists from agents
    intents: Annotated[list, operator.add]  # Combines intents
    
    # Agent outputs
    github_results: Optional[Dict[str, Any]]
    knowledge_results: Optional[Dict[str, Any]]
    collaboration_results: Optional[Dict[str, Any]]
    gmail_results: dict
    calendar_results: dict
    drive_results: dict
    rag_results: dict
    
    # Human-in-the-loop
    pending_human_approval: List[Dict[str, Any]]
    
    # Response
    final_response: str
    confidence_score: float
    iteration_count: int
    
    # Errors
    errors: Annotated[List[str], operator.add]      # Combines errors from agents
