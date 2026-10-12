"""Owner-scoped message lookup for persisted chat receipt updates."""


def message_receipt_snapshot(user_ref, message_id, transaction):
    """Messages have auto document IDs; resolve their stored public ID in the owner scope."""
    matches = list(
        user_ref.collection('messages').where('id', '==', message_id).limit(1).stream(transaction=transaction)
    )
    return matches[0] if matches else None
