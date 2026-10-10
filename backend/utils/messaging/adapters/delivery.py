"""Content-free durable receipts and a transactional iMessage send/receive guard."""

from datetime import datetime, timezone
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from google.cloud import firestore
from database.messaging import MessagingStore
from utils.messaging.identity import key
from utils.executors import db_executor, run_blocking


class DeliveryLedger:
    def __init__(self, store=None):
        self.store = store or MessagingStore()

    def _chat(self, message):
        return (
            self.store.identity(message.channel, message.provider, message.external_user_id)
            .collection('delivery_chats')
            .document(key(message.external_chat_id))
        )

    def inbound(self, message):
        chat = self._chat(message)
        marker = chat.collection('inbound').document(key(message.provider_message_id))

        @firestore.transactional
        def apply(tx):
            seen = marker.get(transaction=tx).exists
            counts = chat.get(transaction=tx).to_dict() or {}
            if not seen:
                tx.create(marker, {'at': datetime.now(timezone.utc)})
                tx.set(chat, {'received': counts.get('received', 0) + 1}, merge=True)

        run_with_transaction_contention_retry(self.store.db.transaction, apply, operation_name='channel_delivery')

    def reserve(self, message, operation, *, ratio=None, retry_reserved=False):
        chat = self._chat(message)
        ref = chat.collection('receipts').document(key(operation))

        @firestore.transactional
        def apply(tx):
            prior = ref.get(transaction=tx).to_dict() or {}
            counts = chat.get(transaction=tx).to_dict() or {}
            if prior.get('state') == 'accepted':
                return False
            if prior:
                if retry_reserved:
                    return True
                raise RuntimeError('Ambiguous delivery requires reconciliation')
            sent, received = counts.get('sent', 0), counts.get('received', 0)
            if ratio is not None and (not received or sent + 1 > received * ratio):
                raise PermissionError('Send/receive ratio exhausted')
            tx.create(ref, {'state': 'reserved', 'at': datetime.now(timezone.utc)})
            tx.set(chat, {'sent': sent + 1}, merge=True)
            return True

        return run_with_transaction_contention_retry(
            self.store.db.transaction, apply, operation_name='channel_delivery'
        )

    def accepted(self, message, operation, provider_id):
        self._chat(message).collection('receipts').document(key(operation)).update(
            {'state': 'accepted', 'provider_id': str(provider_id), 'at': datetime.now(timezone.utc)}
        )

    async def receive(self, message):
        await run_blocking(db_executor, self.inbound, message)

    async def begin(self, message, operation, **kwargs):
        return await run_blocking(db_executor, self.reserve, message, operation, **kwargs)

    async def commit(self, message, operation, provider_id):
        await run_blocking(db_executor, self.accepted, message, operation, provider_id)
