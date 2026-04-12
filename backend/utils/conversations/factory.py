from typing import List, Mapping, Sequence, Union

from models.conversation import Conversation


def hydrate_conversation(data: Union[Conversation, Mapping]) -> Conversation:
    """Convert a raw dict (e.g. from Firestore) into a Conversation object.

    If already a Conversation instance, returns it unchanged.
    Construction goes through Conversation(**data) so __init__ side-effects
    (plugins_results sync, processing_memory_id sync) are preserved.
    """
    if not isinstance(data, Mapping):
        return data
    return Conversation(**data)


def hydrate_conversations(items: Sequence[Union[Conversation, Mapping]]) -> List[Conversation]:
    """Batch-hydrate a sequence of dicts or Conversation objects."""
    return [hydrate_conversation(item) for item in items]
