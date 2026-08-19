"""Private-context classification for provider-executed tool gating.

A tool the model provider runs on its own infrastructure never reaches the
in-process tool executor, so every allowlist, SSRF and redirect control attached
to that executor stops at the trust boundary. Anthropic's server-side
``web_search`` is the case in tree: Anthropic performs the lookup and the query
string leaves for a third party, so whatever the request already carries can be
carried out inside it. Prompt text is not a control over that. The decision to
offer such a tool has to be made where the request is composed, from the
request's own contents.

Classification here reads **literal wire shapes** — which producer emitted each
tool result — and never the content of the messages. A producer this module
cannot positively identify as public-safe is private, so a newly added tool is
private until someone deliberately allowlists it.

Two wire shapes reach this module:

* OpenAI chat-completions (``routers/desktop_chat.py``): assistant messages
  carry ``tool_calls`` with ``id`` and ``function.name``; results arrive as
  ``role: 'tool'`` messages keyed by ``tool_call_id``.
* Anthropic native (the direct lane in ``utils/retrieval/agentic.py``):
  assistant content carries ``type: 'tool_use'`` blocks with ``id`` and
  ``name``; results arrive as ``type: 'tool_result'`` blocks keyed by
  ``tool_use_id``.

Both answer the same question, so both live here rather than being re-derived
per surface.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def flatten_text_blocks(content: object) -> str:
    """Flatten a message ``content`` field to plain text.

    Accepts either a bare string or a list of typed blocks, and ignores every
    block that is not text (images, tool results) — those carry no instruction
    text to inspect.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ''
    return ''.join(
        block.get('text', '')
        for block in content
        if isinstance(block, Mapping) and block.get('type') == 'text' and isinstance(block.get('text'), str)
    )


def openai_messages_carry_private_tool_output(
    messages: object,
    *,
    public_safe_tools: frozenset[str],
    inline_private_markers: Iterable[str] = (),
) -> bool:
    """Whether OpenAI-shaped *messages* already carry private tool output.

    ``inline_private_markers`` covers hosts that splice tool output into a user
    turn behind a literal marker instead of sending a ``tool`` message, so the
    same private data reaches the request with no ``tool_call_id`` to classify.
    """
    if not isinstance(messages, list):
        return False
    tool_name_by_call_id: dict[str, object] = {}
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        tool_calls = message.get('tool_calls')
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if (
                isinstance(call, Mapping)
                and isinstance(call.get('id'), str)
                and isinstance(call.get('function'), Mapping)
            ):
                tool_name_by_call_id[call['id']] = call['function'].get('name')
    for message in messages:
        if not isinstance(message, Mapping) or message.get('role') != 'tool':
            continue
        call_id = message.get('tool_call_id')
        name = tool_name_by_call_id.get(call_id) if isinstance(call_id, str) else None
        if not isinstance(name, str) or name not in public_safe_tools:
            return True
    markers = tuple(inline_private_markers)
    if not markers:
        return False
    return any(
        isinstance(message, Mapping)
        and message.get('role') == 'user'
        and any(marker in flatten_text_blocks(message.get('content')) for marker in markers)
        for message in messages
    )


def anthropic_messages_carry_private_tool_output(
    messages: object,
    *,
    public_safe_tools: frozenset[str],
) -> bool:
    """Whether Anthropic-shaped *messages* already carry private tool output.

    Mirrors :func:`openai_messages_carry_private_tool_output` across the native
    content-block contract: ``tool_use`` blocks name the producer, and the
    ``tool_result`` blocks that quote a ``tool_use_id`` carry what it returned.
    A ``tool_result`` whose producer is unknown — no matching ``tool_use``, or a
    name outside *public_safe_tools* — is private.
    """
    if not isinstance(messages, list):
        return False
    tool_name_by_use_id: dict[str, object] = {}
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get('content')
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, Mapping) and block.get('type') == 'tool_use' and isinstance(block.get('id'), str):
                tool_name_by_use_id[block['id']] = block.get('name')
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get('content')
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, Mapping) or block.get('type') != 'tool_result':
                continue
            use_id = block.get('tool_use_id')
            name = tool_name_by_use_id.get(use_id) if isinstance(use_id, str) else None
            if not isinstance(name, str) or name not in public_safe_tools:
                return True
    return False


def without_tool_named(tool_schemas: object, name: str) -> list:
    """Drop every tool schema carrying *name* from a request's tool list.

    Withholding a provider-executed tool means composing the request without it;
    there is no per-request "disable" flag to set.
    """
    if not isinstance(tool_schemas, list):
        return []
    return [schema for schema in tool_schemas if not (isinstance(schema, Mapping) and schema.get('name') == name)]
