"""Safety boundaries for chat tool results passed back into model context."""

from utils.memory.chat_memory_adapter import CHAT_MEMORY_BOUNDARY_NOTICE, CHAT_MEMORY_POLICY_MARKER

CHAT_MEMORY_TOOL_NAMES = frozenset({'get_memories_tool', 'search_memories_tool'})
CHAT_MEMORY_SAFE_NO_RESULT = "No memories available for this request."


def chat_memory_content_for_classification(result: str) -> str:
    """The untrusted evidence of a memory result, for security screening.

    The adapter wraps evidence with a server-authored boundary notice and policy
    marker telling the model the data is untrusted; that trusted imperative
    would otherwise be classified as an embedded instruction in the tool output.
    """
    trusted_lines = {CHAT_MEMORY_BOUNDARY_NOTICE, CHAT_MEMORY_POLICY_MARKER}
    return '\n'.join(line for line in str(result).splitlines() if line not in trusted_lines)


def preserve_chat_memory_tool_result_boundary(tool_name: str, result: str) -> str:
    """Fail closed if memory memory evidence markers appear without the full quoted boundary.

    The Anthropic tool caller passes string tool output directly back into the
    model as `tool_result.content`. memory chat memory adapters intentionally emit
    untrusted evidence as bounded `content_quoted=...` records. This guard keeps
    downstream caller/wrapper changes from partially preserving those records
    while dropping the boundary notice, policy marker, source marker, or Archive
    default-unavailable marker.
    """

    if tool_name not in CHAT_MEMORY_TOOL_NAMES:
        return result

    text = str(result)
    if not _looks_like_memory_memory_evidence(text):
        return text

    if _has_required_memory_memory_boundary(text):
        return text

    return CHAT_MEMORY_SAFE_NO_RESULT


def _looks_like_memory_memory_evidence(text: str) -> bool:
    markers = ('content_quoted=', 'source_marker=memory_default_memory', 'source_marker=vector_memory')
    return any(marker in text for marker in markers)


def _has_required_memory_memory_boundary(text: str) -> bool:
    if CHAT_MEMORY_BOUNDARY_NOTICE not in text:
        return False
    if CHAT_MEMORY_POLICY_MARKER not in text:
        return False
    if 'archive_default_visible=False' not in text:
        return False
    if 'content_quoted=' not in text:
        return False
    return 'source_marker=memory_default_memory' in text or 'source_marker=vector_memory' in text
