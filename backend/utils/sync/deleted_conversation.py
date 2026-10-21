"""Terminal client answer for completed content whose conversation the user deleted.

A completed receipt whose result names a conversation the user deleted is the
one privacy denial answered terminally: the content was already processed, and
the user's deletion is the final word on it. The answer is ``completed`` with
an empty result and ``reason_code='conversation_deleted'``, so the phone ACKs
its WAL instead of re-uploading the deleted audio. No deleted (or surviving)
conversation ID is ever echoed. Import-light: shared by the legacy status poll
and the batch intake/status paths.
"""

from collections.abc import Callable, Iterable
from typing import Any

from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason

CONVERSATION_DELETED_REASON_CODE = 'conversation_deleted'


def is_conversation_deleted(error: BatchPrivacyBlocked) -> bool:
    return error.reason is BatchPrivacyReason.CONVERSATION_DELETED


def confirm_only_user_deletions(check: Callable[[list[str]], Any], conversation_ids: Iterable[str]) -> None:
    """Re-raise unless every denied conversation ID is a user deletion.

    The privacy walk stops at the first denied ID of an unordered set, so a
    receipt mixing a user deletion with, say, a missing server redirect could
    surface either reason. Re-check each ID alone, in a fixed order, within the
    caller's transaction; any other denial wins and is never acknowledged.
    """
    for conversation_id in sorted(set(conversation_ids)):
        try:
            check([conversation_id])
        except BatchPrivacyBlocked as error:
            if not is_conversation_deleted(error):
                raise


def deleted_conversation_result(total_segments: int) -> dict[str, Any]:
    """An all-success, ID-free result for content whose conversation the user deleted."""
    return {
        'new_memories': [],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': total_segments,
        'errors': [],
    }
