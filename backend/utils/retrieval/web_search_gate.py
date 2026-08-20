"""Per-request gate for Anthropic server-side web_search on the agentic path.

Anthropic executes ``web_search`` on its own infrastructure, so the query never
reaches the in-process tool executor and leaves the trust boundary without any
SSRF or allowlist control. After a private tool result is in the transcript, an
injected instruction can place that data into the query.

The opening request is always clean: ``_messages_to_anthropic`` emits text-only
turns, and taint only appears *during* the loop as tool results are appended.
The offer is therefore re-decided before each provider request and latched once
withheld. Do not hoist the check out of the loop to keep the prompt-cache prefix
stable — a hoisted check can never observe the taint it exists to catch.

``tool_search_tool_regex`` is deliberately not gated: it is provider-executed
too, but it resolves inside Anthropic and reaches no third party.
"""

from __future__ import annotations

from collections.abc import Mapping

from utils.llm.private_context import anthropic_messages_carry_private_tool_output, without_tool_named
from utils.observability.fallback import record_fallback

SERVER_WEB_SEARCH_NAME = "web_search"
WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": SERVER_WEB_SEARCH_NAME,
    "max_uses": 5,
}

# Only product-doc lookups stay public-safe. Every other core tool reads user
# data, echoes the user's input back, or can surface user data in an error
# string. Unknown names — app tools are registered at runtime — are private.
PUBLIC_SAFE_AGENT_TOOLS = frozenset({"get_omi_product_info_tool"})


def request_tools_after_private_taint(
    tool_schemas: object,
    messages: object,
    *,
    withheld: bool,
) -> tuple[list, bool]:
    """Return the tool list for this provider request and the latched withhold flag."""
    schemas = tool_schemas if isinstance(tool_schemas, list) else []
    offers = any(isinstance(schema, Mapping) and schema.get("name") == SERVER_WEB_SEARCH_NAME for schema in schemas)
    if (
        offers
        and not withheld
        and anthropic_messages_carry_private_tool_output(messages, public_safe_tools=PUBLIC_SAFE_AGENT_TOOLS)
    ):
        withheld = True
        record_fallback(
            component="other",
            from_mode="anthropic_web_search",
            to_mode="model_knowledge",
            reason="private_tool_output_in_context",
            outcome="degraded",
        )
    request_tools = without_tool_named(schemas, SERVER_WEB_SEARCH_NAME) if withheld else schemas
    return request_tools, withheld
