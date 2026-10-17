"""Encrypted, versioned shaped-context state and owner-scoped summary source pages."""

import json
from datetime import datetime

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from database.messaging import MessagingStore
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database import chat as chat_db
from utils import encryption
from database import chat_context_prefetch


class ChatContextStore:
    def __init__(self, *, messaging=None):
        self.messaging = messaging or MessagingStore()

    def load_for_turn(self, uid, session_id):
        return chat_context_prefetch.load(self.messaging, uid, session_id)

    def validate_for_turn(self, uid, session_id, state, timeout):
        chat_context_prefetch.validate(self.messaging, uid, session_id, state, timeout)

    def assert_access(self, uid, session_id):
        ref = self.messaging.user(uid).collection('chat_sessions').document(session_id)

        @firestore.transactional
        def check(tx):
            row = ref.get(transaction=tx).to_dict()
            if not row:
                raise PermissionError('Session removed')
            user = self.messaging.assert_session_link(tx, uid, row)
            return row, user

        return run_with_transaction_contention_retry(
            self.messaging.db.transaction, check, operation_name='context_read_guard'
        )

    def load(self, uid, session_id):
        # Reuse the guarded transaction's snapshots: the old path reread both
        # documents serially and could observe a session removed after its guard.
        row, user = self.assert_access(uid, session_id)
        version = user.get('chat_context_generation', 0)
        state = json.loads(encryption.decrypt(row['shaped_context'], uid)) if row.get('shaped_context') else {}
        if state.get('generation', 0) != version:
            state = {}
        return dict(state, generation=version, revision=row.get('shaped_context_revision', 0))

    def save(self, uid, session_id, state, expected_revision):
        ref = self.messaging.user(uid).collection('chat_sessions').document(session_id)
        payload = encryption.encrypt(json.dumps(state), uid)

        @firestore.transactional
        def apply(tx):
            row = ref.get(transaction=tx).to_dict()
            user = self.messaging.user(uid).get(transaction=tx).to_dict() or {}
            if not row:
                raise PermissionError('Session removed')
            self.messaging.assert_session_link(tx, uid, row)
            if user.get('chat_context_generation', 0) != state['generation']:
                raise PermissionError('Chat changed during context preparation')
            if row.get('shaped_context_revision', 0) != expected_revision:
                raise RuntimeError('Concurrent context preparation; retry turn')
            tx.update(ref, {'shaped_context': payload, 'shaped_context_revision': expected_revision + 1})

        run_with_transaction_contention_retry(self.messaging.db.transaction, apply, operation_name='shaped_context')

    def source_page(self, uid, session_id, before_id, cursor=None, limit=40):
        self.assert_access(uid, session_id)
        collection = self.messaging.user(uid).collection('messages')
        # App add_message uses Firestore .add(): its document ID is independent
        # of Message.id. Channels happen to use matching IDs. Resolve the wire
        # identity in the owner's collection, then use the actual snapshot cursor.
        boundaries = list(collection.where(filter=FieldFilter('id', '==', before_id)).limit(2).stream())
        if len(boundaries) != 1:
            raise PermissionError('Context boundary missing or ambiguous')
        boundary = boundaries[0]
        row = boundary.to_dict() or {}
        if row.get('chat_session_id') != session_id:
            raise PermissionError('Context boundary outside session')
        query = (
            collection.where(filter=FieldFilter('chat_session_id', '==', session_id))
            .order_by('created_at')
            .order_by('__name__')
            .end_before(boundary)
        )
        if cursor:
            query = query.start_after(
                {'created_at': datetime.fromisoformat(cursor['at']), '__name__': collection.document(cursor['id'])}
            )
        documents = list(query.limit(limit).stream())
        messages = []
        for doc in documents:
            row = doc.to_dict() or {}
            if row.get('reported') is not True and not chat_db.is_automatic_chat_message(row):
                row = chat_db.decrypt_message_payload(row, uid)
                text = row.get('text', '')
                if row.get('files_id'):
                    text += '\n[Files attached: ' + ', '.join(row['files_id']) + ']'
                messages.append({'role': 'assistant' if row.get('sender') == 'ai' else 'user', 'content': text})
        next_cursor = (
            {'id': documents[-1].id, 'at': documents[-1].to_dict()['created_at'].isoformat()} if documents else cursor
        )
        return messages, next_cursor, len(documents) == limit
