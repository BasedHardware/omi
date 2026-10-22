"""Owner-scoped message lookup for persisted chat receipt updates."""

from typing import Any


def message_receipt_snapshot(user_ref: Any, message_id: str, transaction: Any) -> Any | None:
    """Messages have auto document IDs; resolve their stored public ID in the owner scope.

    Preserves input validation while allowing transactional contention errors to propagate.
    """
    if user_ref is None or not (message_id and str(message_id).strip()):
        return None
    clean_id = str(message_id).strip()
    query = user_ref.collection("messages").where("id", "==", clean_id).limit(1)
    matches = list(query.stream(transaction=transaction))
    return matches[0] if matches else None
