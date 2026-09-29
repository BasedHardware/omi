import logging
from typing import Any, Callable, List, Mapping, Optional, Sequence, Union

from models.conversation import Conversation

logger = logging.getLogger(__name__)


def deserialize_conversation(data: Union[Conversation, Mapping[str, Any]]) -> Conversation:
    """Convert a raw dict (e.g. from Firestore) into a Conversation object.

    If already a Conversation instance, returns it unchanged.
    Construction goes through Conversation(**data) so __init__ side-effects
    (plugins_results sync, processing_memory_id sync) are preserved.
    """
    if not isinstance(data, Mapping):
        return data
    return Conversation(**data)


def deserialize_conversations(
    items: Sequence[Union[Conversation, Mapping[str, Any]]],
    on_error: Optional[Callable[[Union[Conversation, Mapping[str, Any]], Exception], None]] = None,
) -> List[Conversation]:
    """Batch-deserialize a sequence of dicts or Conversation objects.

    Skips any malformed records that fail validation, logging a warning,
    so that one corrupted or legacy document cannot break batch operations
    (such as RAG retrieval, Wrapped year-in-review, and developer queries).
    Mirrors Person.deserialize_many_safe and Message.deserialize_many_safe.
    """
    results: List[Conversation] = []
    for item in items:
        if not isinstance(item, (Conversation, Mapping)):
            continue
        try:
            conv = deserialize_conversation(item)
            if isinstance(conv, Conversation):
                results.append(conv)
        except Exception as exc:  # noqa: BLE001 - one bad record must not break the batch
            if on_error is not None:
                on_error(item, exc)
            else:
                logger.warning(f"Skipping malformed conversation record during batch deserialization: {exc}")
    return results


deserialize_conversations_safe = deserialize_conversations
