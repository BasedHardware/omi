"""
Tools for answering questions about the Omi/Friend product.
"""

from collections.abc import Mapping
from typing import Optional

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from utils.app_integrations import get_github_docs_content
import logging

try:
    from utils.retrieval.tools.result_bounds import bounded_result, cap_items_for_llm
except ModuleNotFoundError:
    import importlib.util as _importlib_util
    import sys as _sys
    from pathlib import Path as _Path

    _rb_spec = _importlib_util.spec_from_file_location(
        "utils.retrieval.tools.result_bounds",
        str(_Path(__file__).resolve().with_name("result_bounds.py")),
    )
    assert _rb_spec is not None and _rb_spec.loader is not None
    _rb_mod = _importlib_util.module_from_spec(_rb_spec)
    # Register before exec (the load_module_fresh recipe): the loaded module's
    # own fallback import resolves dataclass annotations via sys.modules.
    _sys.modules["utils.retrieval.tools.result_bounds"] = _rb_mod
    _rb_spec.loader.exec_module(_rb_mod)
    bounded_result = _rb_mod.bounded_result
    cap_items_for_llm = _rb_mod.cap_items_for_llm

logger = logging.getLogger(__name__)

MAX_DOC_SECTIONS = 100


@tool
def get_omi_product_info_tool(query: Optional[str] = None) -> str:
    """
    Get information about the Omi/Friend product to answer questions about features, functionality, setup, or purchasing.

    Use this tool when the user asks about:
    - How Omi/Friend works
    - What features the app/device has
    - How to set up or use Omi
    - Where to buy the device or pricing information
    - Technical specifications (battery life, connectivity, etc.)
    - App capabilities and functionality
    - Firmware updates or device management
    - Troubleshooting product issues

    DO NOT use this tool for:
    - Questions about the user's personal conversations or memories
    - Questions about what the user said or did
    - Action items or reminders
    - Personal data queries

    Args:
        query: The specific question about Omi/Friend product (e.g., "How does the device connect to my phone?", "What is the battery life?")

    Returns:
        Product documentation content from GitHub that can help answer the question

    Example:
        query="How do I update the firmware on my Omi device?"
        Returns documentation about firmware updates and device management
    """
    if query is None or not isinstance(query, str) or not query.strip():  # type: ignore[reportUnnecessaryIsInstance]  # defensive runtime guard: the LLM tool boundary may pass junk despite the annotation
        return "Error: Please provide a non-empty question or query about the Omi/Friend product."

    # Fetch the product docs. A network or GitHub API failure must not break the chat turn, so fail
    # soft with an "Error: ..." string like the other retrieval tools instead of letting the
    # exception escape into the agent loop.
    try:
        context = get_github_docs_content()
    except Exception as e:
        logger.warning(f"get_omi_product_info_tool - failed to fetch product docs: {e}")
        return (
            "Error: the Omi product documentation could not be retrieved right now. Tell the user "
            "that product information is temporarily unavailable and to try again in a little while."
        )

    if not context or not isinstance(context, Mapping):
        # An empty result (e.g. the GitHub API returned non-200) would otherwise produce a docs
        # string with no real content, which misleads the model into answering from nothing. Log it
        # so a silent "no docs" state is diagnosable in prod, not only visible to the user.
        logger.warning("get_omi_product_info_tool - product docs fetch returned no content")
        return (
            "No Omi product documentation is available right now. Tell the user that product "
            "information is temporarily unavailable and to try again in a little while."
        )

    sections, _, sections_truncated = cap_items_for_llm(list(context.items()), MAX_DOC_SECTIONS)

    # Format context as a comprehensive documentation string
    context_str = 'Omi/Friend Product Documentation:\n\n'
    for section, content in sections:
        if content is None:
            continue
        context_str += f'## {section}\n\n{content}\n\n'

    context_str += (
        '\n\nUse this documentation to answer questions about the Omi/Friend product, its features, setup, and usage.'
    )

    return bounded_result(
        context_str,
        sections_truncated,
        noun="documentation sections",
        shown=len(sections) if sections_truncated else None,
    )
