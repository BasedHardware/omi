"""
Bounded read-only knowledge-graph traversal for agentic chat (WS-N).
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any, Dict, Optional, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed

from utils.memory.kg_graph_traversal import format_traversal_result, traverse_knowledge_graph

logger = logging.getLogger(__name__)

try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar("agent_config", default=None)


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve the agent config dict from the context var, or None if unset."""
    try:
        return agent_config_context.get()
    except LookupError:
        return None


def _resolve_uid(config: RunnableConfig | None) -> Optional[str]:
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
    if not cfg:
        return None
    try:
        raw_configurable = cfg.get('configurable')
        if isinstance(raw_configurable, dict):
            configurable: Dict[str, Any] = cast(Dict[str, Any], raw_configurable)
            return configurable.get('user_id')
        return None
    except (KeyError, TypeError):
        return None


@tool
def traverse_knowledge_graph_tool(
    entity: str,
    hops: int = 1,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Traverse the user's knowledge graph to find related entities and relationships.

    Use this for multi-hop relationship questions that flat memory search cannot answer,
    e.g. "how does my job relate to where I live?" or "who is connected to project X?".

    Read-only: never modifies the graph. Bounded to at most 2 hops with fan-out caps.

    Args:
        entity: Entity name or alias to start from (person, place, organization, concept).
        hops: How many relationship hops to expand (1 or 2; values above 2 are capped).

    Returns:
        Connected subgraph of relationships with cited long-term memory atoms.
    """
    logger.info("traverse_knowledge_graph_tool entity=%s hops=%s", entity, hops)

    uid = _resolve_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"

    try:
        result = traverse_knowledge_graph(uid, entity, hops=hops)
        return format_traversal_result(result)
    except Exception as exc:
        logger.exception("traverse_knowledge_graph_tool failed uid=%s: %s", uid, exc)
        return f"Error traversing knowledge graph: {exc}"
