"""Snapshot-bound status transitions used only by the lifecycle owner."""

from google.cloud import firestore
from database._client import get_firestore_client, run_transactional
from database.people_stats_cache import invalidate_people_stats_cache


def transition_conversation_status(uid: str, conversation_id: str, status: str, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection('conversations').document(conversation_id)

    @firestore.transactional
    def _transition(transaction):
        snapshot = conversation_ref.get(transaction=transaction)
        if not snapshot.exists:
            return
        current = snapshot.to_dict() or {}
        updates = {'status': status}
        if getattr(status, 'value', status) == 'completed':
            from utils.conversations.terminal_relevance import stamp_terminal_decision

            result = {**current, **updates}
            stamp_terminal_decision(result, path='lifecycle_terminal')
            updates['relevance_decision'] = result['relevance_decision']
        transaction.update(conversation_ref, updates)

    run_transactional(client, _transition)
    invalidate_people_stats_cache(uid)


def recovery_discard_payload(write_data: dict) -> bool:
    # Imported lazily: several unit harnesses load this module with a stubbed
    # ``utils`` package that has no ``utils.conversations`` subpackage.
    from utils.conversations.recovery import verified_recovery_discard

    return verified_recovery_discard(write_data.get('discarded'), write_data.get('relevance_decision'))
