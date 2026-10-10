"""Durable messaging identities, single-use proofs, inbox and fenced surface leases.

New clients are lazy and injectable. Payloads are encrypted, never exported to
training or analytics. No raw webhook body is retained.
"""

import json
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from database.firestore_transaction_retry import run_with_transaction_contention_retry
from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists

from database._client import get_firestore_client
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from utils import encryption
from utils.messaging.identity import key

_LINK_SETTINGS = ('visible_in_app', 'voice_notes', 'keep_private_memories_in_app', 'insights')
_SETTING_DEFAULTS = {
    'visible_in_app': False,
    'voice_notes': True,
    'keep_private_memories_in_app': True,
    'insights': False,
}


class MessagingStore:
    def __init__(self, *, firestore_client=None):
        self._client = firestore_client

    @property
    def db(self):
        return self._client if self._client is not None else get_firestore_client()

    def user(self, uid):
        return self.db.collection('users').document(uid)

    def identity(self, channel, provider, external_id):
        return self.db.collection('channel_identities').document(key(channel, provider, external_id))

    def mint(self, uid, channel, provider, kind, *, now=None):
        now = now or datetime.now(timezone.utc)
        if kind not in ('token', 'code'):
            raise ValueError('Unknown proof kind')
        # Both have >100 bits of entropy. Codes are human copy/pasteable, not short PINs.
        proof = secrets.token_urlsafe(24) if kind == 'token' else secrets.token_hex(16).upper()
        proof_id = key(proof)
        expires = now + timedelta(minutes=10)
        payload = dict(uid=uid, channel=channel, provider=provider, kind=kind, expires_at=expires)
        batch = self.db.batch()
        batch.create(self.db.collection('channel_link_proofs').document(proof_id), payload)
        batch.set(self.user(uid).collection('channel_link_proofs').document(proof_id), {'expires_at': expires})
        batch.commit()
        return {'proof': proof, 'kind': kind, 'expires_at': expires}

    def consume(self, proof, message, *, now=None):
        now = now or datetime.now(timezone.utc)
        proof_ref = self.db.collection('channel_link_proofs').document(key(proof))
        identity = self.identity(message.channel, message.provider, message.external_user_id)

        @firestore.transactional
        def apply(tx):
            token = proof_ref.get(transaction=tx).to_dict()
            existing = identity.get(transaction=tx).to_dict() or {}
            if not token or token['expires_at'] <= now:
                raise PermissionError('Invalid or expired link proof')
            if (token['channel'], token['provider']) != (message.channel, message.provider):
                raise PermissionError('Link proof has a different audience')
            uid = token['uid']
            user = self.user(uid).get(transaction=tx).to_dict()
            deletion = account_deletion_document(uid, firestore_client=self.db).get(transaction=tx)
            if _deletion_blocks(deletion):
                raise PermissionError('Account deletion in progress')
            if not user or user.get('deleted') or user.get('deletion_requested_at'):
                raise PermissionError('Account unavailable')
            if existing.get('uid') and existing['uid'] != uid:
                raise PermissionError('Identity already linked')
            link = dict(
                uid=uid,
                channel=message.channel,
                provider=message.provider,
                external_id=message.external_user_id,
                generation=existing.get('generation') if existing.get('active') else str(uuid4()),
                linked_at=now,
                active=True,
                display_handle=_display_handle(getattr(message, 'display_name', None))
                or existing.get('display_handle'),
            )
            for name, default in _SETTING_DEFAULTS.items():
                link[name] = existing.get(name, default)
            tx.set(identity, link)
            tx.set(self.user(uid).collection('channel_links').document(identity.id), link)
            tx.delete(proof_ref)
            tx.delete(self.user(uid).collection('channel_link_proofs').document(proof_ref.id))
            return link

        return run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_transaction')

    def lookup(self, message):
        return self.identity(message.channel, message.provider, message.external_user_id).get().to_dict()

    def links(self, uid):
        return [dict(doc.to_dict(), id=doc.id) for doc in self.user(uid).collection('channel_links').stream()]

    def set_visibility(self, uid, link_id, visible):
        self.set_settings(uid, link_id, {'visible_in_app': visible})

    def set_settings(self, uid, link_id, updates):
        patch = {name: updates[name] for name in _LINK_SETTINGS if name in updates and updates[name] is not None}
        if not patch or any(not isinstance(value, bool) for value in patch.values()):
            raise ValueError('No settings')
        ref = self.user(uid).collection('channel_links').document(link_id)
        if not ref.get().exists:
            raise PermissionError('Link not found')
        batch = self.db.batch()
        batch.update(ref, patch)
        batch.update(self.db.collection('channel_identities').document(link_id), patch)
        batch.commit()

    def unlink(self, uid, link_id):
        mirror = self.user(uid).collection('channel_links').document(link_id)
        identity = self.db.collection('channel_identities').document(link_id)

        @firestore.transactional
        def revoke(tx):
            link = identity.get(transaction=tx).to_dict() or {}
            if link.get('uid') != uid:
                raise PermissionError('Link not found')
            tx.update(identity, {'active': False, 'generation': str(uuid4())})
            return link

        run_with_transaction_contention_retry(self.db.transaction, revoke, operation_name='messaging_revoke')
        # Revocation precedes deletion. Workers re-check immediately before every send.
        for session in self.user(uid).collection('chat_sessions').stream():
            data = session.to_dict()
            if data.get('channel_link_id') == link_id:
                self.db.recursive_delete(session.reference)
        for message in self.user(uid).collection('messages').stream():
            if message.to_dict().get('channel_link_id') == link_id:
                message.reference.delete()
        self.db.recursive_delete(identity)
        mirror.delete()

    def delete_account(self, uid):
        for link in self.links(uid):
            self.unlink(uid, link['id'])
        for proof in self.user(uid).collection('channel_link_proofs').stream():
            self.db.collection('channel_link_proofs').document(proof.id).delete()
            proof.reference.delete()

    def enqueue(self, message):
        identity = self.identity(message.channel, message.provider, message.external_user_id)
        try:
            identity.create({'channel': message.channel, 'provider': message.provider, 'active': False})
        except AlreadyExists:
            pass
        # Provider message ids may only be unique within a chat.
        ref = identity.collection('inbox').document(key(message.external_chat_id, message.provider_message_id))
        payload = asdict(message)
        payload['received_at'] = message.received_at.isoformat()
        try:
            ref.create(
                {
                    'payload': encryption.encrypt(json.dumps(payload), identity.id),
                    'status': 'pending',
                    'created_at': datetime.now(timezone.utc),
                }
            )
        except AlreadyExists:
            return None
        return ref.path

    def claim(self, path):
        ref = self.db.document(path)

        @firestore.transactional
        def apply(tx):
            row = ref.get(transaction=tx).to_dict()
            if not row or row['status'] != 'pending':
                return None
            tx.update(ref, {'status': 'running'})
            return json.loads(encryption.decrypt(row['payload'], ref.parent.parent.id))

        return run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_transaction')

    def complete(self, path):
        # Content-free dedup tombstone survives retries; unlink removes its parent.
        self.db.document(path).update({'status': 'done', 'payload': firestore.DELETE_FIELD})

    def acquire(self, uid, surface):
        ref = self.user(uid).collection('channel_turn_leases').document(key(surface))
        token = str(uuid4())
        try:
            ref.create({'token': token, 'created_at': datetime.now(timezone.utc)})
        except AlreadyExists:
            return None
        return token

    def release(self, uid, surface, token):
        ref = self.user(uid).collection('channel_turn_leases').document(key(surface))

        @firestore.transactional
        def apply(tx):
            row = ref.get(transaction=tx).to_dict()
            if not row or row['token'] != token:
                raise PermissionError('Lost surface lease')
            tx.delete(ref)

        run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_transaction')

    def session(self, uid, message, link):
        surface = 'channel:' + key(message.channel, message.external_chat_id)
        ref = self.user(uid).collection('chat_sessions').document(key(surface))
        now = datetime.now(timezone.utc)
        row = dict(
            id=ref.id,
            surface=surface,
            channel=message.channel,
            link_generation=link['generation'],
            channel_link_id=key(message.channel, message.provider, message.external_user_id),
            plugin_id='__channel__',
            created_at=now,
            updated_at=now,
            message_ids=[],
            file_ids=[],
            title='Channel chat',
        )
        try:
            ref.create(row)
        except AlreadyExists:
            row = ref.get().to_dict()
        if row.get('channel_link_id') != key(message.channel, message.provider, message.external_user_id):
            raise PermissionError('Surface belongs to another link')
        return row

    def events(self, uid, session_id):
        ref = self.user(uid).collection('chat_sessions').document(session_id)
        return [
            json.loads(encryption.decrypt(d.to_dict()['payload'], uid))
            for d in ref.collection('channel_events').order_by('__name__').stream()
        ]

    def append_event(self, uid, session_id, event):
        ref = self.user(uid).collection('chat_sessions').document(session_id)
        # Called under a non-stealable surface lease. Prefix is never modified.
        events = self.events(uid, session_id)
        if any(e['id'] == event['id'] for e in events):
            return
        if sum(len(json.dumps(e)) for e in events) + len(json.dumps(event)) > 500_000:
            raise ValueError('Surface history budget reached; explicit new session required')
        payload = {'payload': encryption.encrypt(json.dumps(event), uid)}

        @firestore.transactional
        def apply(tx):
            session = ref.get(transaction=tx).to_dict()
            if not session:
                raise PermissionError('Session removed')
            self.assert_session_link(tx, uid, session)
            tx.create(ref.collection('channel_events').document(f'{len(events):012d}'), payload)

        run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_transaction')

    def retry(self, path):
        self.db.document(path).update({'status': 'pending'})

    def pending(self, message):
        """Recovery seam: Stage B's dispatcher periodically scans its owned identities."""
        return [
            d.reference.path
            for d in self.identity(message.channel, message.provider, message.external_user_id)
            .collection('inbox')
            .stream()
            if d.to_dict().get('status') == 'pending'
        ]

    def assert_session_link(self, tx, uid, session):
        user = self.user(uid).get(transaction=tx).to_dict()
        deletion = account_deletion_document(uid, firestore_client=self.db).get(transaction=tx)
        if not user or _deletion_blocks(deletion):
            raise PermissionError('Account removed or deleting')
        link_id = session.get('channel_link_id')
        if link_id:
            link = self.db.collection('channel_identities').document(link_id).get(transaction=tx).to_dict() or {}
            if not link.get('active') or link.get('uid') != uid or link.get('generation') != session['link_generation']:
                raise PermissionError('Link revoked')

    def persist_message(self, uid, document, session_id):
        session_ref = self.user(uid).collection('chat_sessions').document(session_id)
        payload = dict(document, text=encryption.encrypt(document['text'], uid), data_protection_level='enhanced')
        payload.pop('memories', None)

        @firestore.transactional
        def apply(tx):
            session = session_ref.get(transaction=tx).to_dict()
            if not session:
                raise PermissionError('Session removed')
            self.assert_session_link(tx, uid, session)
            tx.set(self.user(uid).collection('messages').document(document['id']), payload)
            tx.update(session_ref, {'updated_at': datetime.now(timezone.utc)})

        run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_transaction')
        return document

    def proof_owner(self, proof):
        row = self.db.collection('channel_link_proofs').document(key(proof)).get().to_dict()
        if not row:
            raise PermissionError('Invalid proof')
        return row['uid']

    def pending_jobs(self, channel, provider, limit=100):
        paths = []
        for identity in self.db.collection('channel_identities').stream():
            row = identity.to_dict()
            if (row.get('channel'), row.get('provider')) != (channel, provider):
                continue
            for event in identity.reference.collection('inbox').stream():
                if event.to_dict().get('status') == 'pending':
                    paths.append(event.reference.path)
                    if len(paths) >= limit:
                        return paths
        return paths


def _display_handle(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lstrip('@')
    if not value or len(value) > 64 or any(character.isspace() for character in value):
        return None
    return value


def _deletion_blocks(snapshot):
    return account_deletion_blocks_access(
        normalize_account_deletion_status(
            marker_exists=snapshot.exists, raw_status=(snapshot.to_dict() or {}).get('wipe_status')
        )
    )
