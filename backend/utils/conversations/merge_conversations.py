<content>
import logging
from typing import List

from backend.database.vector_db import delete_action_item_vectors_batch
from backend.database.vector_db import find_similar_action_items
from backend.database.vector_db import upsert_action_item_vector
from backend.models.conversations import Conversation
from backend.models.tasks import Task
from backend.utils.conversations import delete_conversation_and_related_data

logger = logging.getLogger(__name__)


def merge_conversations(
    user_id: str, source_conversation_ids: List[str], target_conversation_id: str
) -> Conversation:
    """
    Merge multiple conversations into one target conversation.

    Args:
        user_id: The ID of the user performing the merge.
        source_conversation_ids: A list of conversation IDs to merge.
        target_conversation_id: The ID of the target conversation to merge into.

    Returns:
        The merged Conversation object.
    """
    if not source_conversation_ids:
        raise ValueError("Source conversation IDs cannot be empty.")

    # Get the target conversation
    target_conversation = Conversation.find_by_id(target_conversation_id)
    if not target_conversation:
        raise ValueError(f"Target conversation with ID {target_conversation_id} not found.")
    if target_conversation.user_id != user_id:
        raise ValueError("User does not have permission to access the target conversation.")

    # Get all source conversations
    source_conversations = []
    for conv_id in source_conversation_ids:
        conv = Conversation.find_by_id(conv_id)
        if not conv:
            logger.warning(f"Source conversation with ID {conv_id} not found. Skipping.")
            continue
        if conv.user_id != user_id:
            logger.warning(
                f"User does not have permission to access source conversation {conv_id}. Skipping."
            )
            continue
        source_conversations.append(conv)

    if not source_conversations:
        raise ValueError("No valid source conversations found to merge.")

    # Collect all task IDs from the source conversations to delete their vectors
    task_ids_to_delete_vectors = []
    for source_conv in source_conversations:
        for task in source_conv.tasks:
            task_ids_to_delete_vectors.append(task.id)

    # Delete the source conversations and their related data (tasks, etc.)
    for source_conv in source_conversations:
        delete_conversation_and_related_data(user_id, source_conv.id)

    # Delete the Pinecone vectors for the removed tasks
    if task_ids_to_delete_vectors:
        delete_action_item_vectors_batch(user_id, task_ids_to_delete_vectors)

    # Return the merged conversation
    return target_conversation
</content>