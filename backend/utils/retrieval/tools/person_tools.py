"""
Tool for retrieving context about a specific person the user talks to.
"""

import contextvars
import logging

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from utils.retrieval.tool_services.person_service import get_person_context

logger = logging.getLogger(__name__)

try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


@tool
def get_person_context_tool(person: str, config: RunnableConfig = None) -> str:
    """
    Retrieve everything Omi knows about a specific PERSON the user talks to
    (a contact / someone they message or meet), so you can answer questions about
    that person or personalize a reply to them.

    Use this tool when:
    - The user asks about a specific person ("what do I know about Alice?",
      "what's going on with my brother?", "catch me up on Sam").
    - You are drafting a message TO someone and need context on your history and
      tone with them.

    Returns the person's relationship, a profile summary, how the user typically
    talks with them, known facts about them, and recent conversation snippets.
    If nothing is found, say you don't have anything about that person — NEVER
    fabricate details.

    Args:
        person: the person's name, or their phone number / email handle.
    """
    if config is None:
        try:
            config = agent_config_context.get()
        except LookupError:
            config = None
    if config is None:
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError):
        return "Error: Configuration not available"
    if not uid:
        return "Error: User ID not found in configuration"

    try:
        return get_person_context(uid, person)
    except Exception as e:
        logger.error(f"get_person_context_tool failed: {e}")
        return f"Error retrieving context for {person}."
