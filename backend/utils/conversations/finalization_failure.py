"""Pure classification of a failed earlier-conversation finalization in a listen session.

No IO: string and type checks over the exception only. The Firestore message
names the rejected document by its uid-bearing path, so callers log only the
bounded tokens returned here, never the message.
"""

from __future__ import annotations

from dataclasses import dataclass

from database._client import firestore_document_kind, firestore_error_document_path, firestore_failure_reason


@dataclass(frozen=True)
class FinalizationFailure:
    # ``document_size_limit`` | ``expired_transaction`` | ``contention`` | ``other``
    reason: str
    # ``firestore_document_kind`` token for the rejected document.
    document: str
    # The rejection names this conversation's own document (permanent only for it).
    names_conversation: bool

    @property
    def conversation_at_size_limit(self) -> bool:
        return self.reason == 'document_size_limit' and self.names_conversation


def classify_finalization_failure(error: BaseException, conversation_id: str) -> FinalizationFailure:
    segments = firestore_error_document_path(error)
    names_conversation = (
        segments is not None
        and len(segments) == 4
        and segments[0] == 'users'
        and segments[2] == 'conversations'
        and segments[3] == conversation_id
    )
    return FinalizationFailure(
        reason=firestore_failure_reason(error),
        document=firestore_document_kind(error),
        names_conversation=names_conversation,
    )
