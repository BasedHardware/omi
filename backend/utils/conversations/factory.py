from typing import List, Mapping, Sequence, Union

from models.conversation import Conversation


def deserialize_conversation(data: Union[Conversation, Mapping]) -> Conversation:
    """Convert a raw dict (e.g. from Firestore) into a Conversation object.

    If already a Conversation instance, returns it unchanged.
    Construction goes through Conversation(**data) so __init__ side-effects
    (plugins_results sync, processing_memory_id sync) are preserved.
    """
    if not isinstance(data, Mapping):
        return data
    return Conversation(**data)


def deserialize_conversations(items: Sequence[Union[Conversation, Mapping]]) -> List[Conversation]:
    """Batch-deserialize a sequence of dicts or Conversation objects."""
    return [deserialize_conversation(item) for item in items]
