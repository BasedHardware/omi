"""Owner-scoped message lookup for persisted chat receipt updates."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def message_receipt_snapshot(user_ref: Any, message_id: str, transaction: Any) -> Any | None:
    """Messages have auto document IDs; resolve their stored public ID in the owner scope."""
    if user_ref is None or not (message_id and str(message_id).strip()):
        return None
    clean_id = str(message_id).strip()
    try:
        query = user_ref.collection('messages').where('id', '==', clean_id).limit(1)
        matches = list(query.stream(transaction=transaction))
        return matches[0] if matches else None
    except Exception as exc:
        logger.warning("Failed to lookup message receipt snapshot for message %s: %s", clean_id, exc)
        return None
