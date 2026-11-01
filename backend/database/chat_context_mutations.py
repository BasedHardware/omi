"""Erase affected derived context in the same atomic history mutation."""

from google.cloud import firestore


def invalidate_sessions(writer, user_ref, session_ids, *, transaction=None):
    # All reads precede writes. Update existing sessions only: never resurrect one.
    refs = [
        user_ref.collection('chat_sessions').document(s)
        for s in sorted({s for s in session_ids if isinstance(s, str) and s})
    ]
    existing = [ref for ref in refs if ref.get(transaction=transaction).exists]
    for ref in existing:
        writer.update(ref, invalidation_fields())


def invalidation_fields():
    return {'shaped_context': firestore.DELETE_FIELD, 'shaped_context_revision': firestore.Increment(1)}
