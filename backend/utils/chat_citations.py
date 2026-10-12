"""Final in-app/channel answers share the conversation-card citation contract."""

import re
from typing import Any

from utils.messaging.adapters.rendering import CITATION_PATTERN


def resolve_conversation_citations(text: str, conversations: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Strip source markers and select their supplied one-based conversation cards.

    Preserve first mention order so the bounded card list is deterministic. Numeric
    Markdown links remain links; channel adapters separately own Markdown rendering.
    Unknown markers are stripped too, without inventing a source.
    """
    indices = dict.fromkeys(
        int(index) for marker in re.finditer(CITATION_PATTERN, text) for index in re.findall(r'\d+', marker.group(0))
    )
    return re.sub(CITATION_PATTERN, '', text), [
        conversations[index - 1] for index in indices if 0 < index <= len(conversations)
    ]
