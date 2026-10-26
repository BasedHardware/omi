"""
Bounded read-only knowledge-graph traversal for agentic chat (WS-N).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed

from utils.log_sanitizer import sanitize
from utils.memory.kg_graph_traversal import format_traversal_result, traverse_knowledge_graph
from utils.retrieval.tools.integration_base import resolve_config_uid

logger = logging.getLogger(__name__)


def _resolve_uid(config: Optional[Any] = None) -> Optional[str]:
    """Extract uid from config via shared resolve_config_uid."""
    uid, _ = resolve_config_uid(config)
    return uid


@tool
def traverse_knowledge_graph_tool(
    entity: str,
    hops: int | float | str | None = 1,
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

    clean_entity = str(entity or "").strip()
    if not clean_entity:
        return "Error: Entity name cannot be empty."

    try:
        if isinstance(hops, bool):
            parsed_hops = 1
        elif hops is not None:
            parsed_hops = int(float(hops))
        else:
            parsed_hops = 1
    except (TypeError, ValueError):
        parsed_hops = 1

    # Clamp hops to [1, 2], matching MAX_TRAVERSAL_HOPS in utils.memory.kg_graph_traversal.
    parsed_hops = max(1, min(parsed_hops, 2))

    uid, _ = resolve_config_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"

    try:
        result = traverse_knowledge_graph(uid, clean_entity, hops=parsed_hops)
        return format_traversal_result(result)
    except Exception as exc:
        logger.exception("traverse_knowledge_graph_tool failed uid=%s: %s", uid, sanitize(str(exc)))
        return "Error traversing knowledge graph: Unable to complete traversal."
