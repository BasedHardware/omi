"""Durable messaging identities, single-use proofs, inbox and fenced surface leases.

New clients are lazy and injectable. Payloads are encrypted, never exported to
training or analytics. No raw webhook body is retained.
"""

import json
import logging
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any

from config.messaging import channel_policy
from utils.messaging.access import SeatFull, AccessDenied
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from google.cloud import firestore
from prometheus_client import Counter
from google.api_core.exceptions import AlreadyExists

from database.messaging_albums import read_album, append_album, seal_album
from database._client import get_firestore_client
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from utils import encryption
from utils.messaging.identity import key, advances_inbound_head
from utils.observability.fallback import record_fallback

# A worker is bounded to 180s; allow 120s for cancellation/provider cleanup.
TURN_TIMEOUT_SECONDS = 180
STALE_SECONDS = 300
PENDING_MAX_SECONDS = 1800
_QUEUE_EVENTS = Counter('omi_messaging_queue_events_total', 'Messaging queue decisions', ['reason'])


def _queue_event(reason, path, age):
    _QUEUE_EVENTS.labels(reason=reason).inc()
    if reason in {'stale_running', 'stale_pending', 'stale_lease'}:
        record_fallback(component='other', from_mode='channel_turn', to_mode='none', reason='other', outcome='degraded')
    logging.getLogger(__name__).warning('Messaging queue reason=%s path=%s head_age_seconds=%.1f', reason, path, age)


def _age(row, now, field='created_at'):
    return (now - (row.get(field) or row['created_at'])).total_seconds()


_LINK_SETTINGS = ('visible_in_app', 'voice_notes', 'keep_private_memories_in_app', 'insights')
_SETTING_DEFAULTS = {
    'visible_in_app': False,
    'voice_notes': True,
    'keep_private_memories_in_app': True,
    'insights': False,
}


def can_supersede(message):
    """A plain user message (text or media) may replace a reply still being written.

    Commands, button callbacks, link proofs and album parts never interrupt a turn.
    """
    return (
        message.command is None
        and not message.callback_id
        and not message.link_proof
        and not message.unlink
        and not message.media_group_id
    )


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
        self.check_capacity(uid, channel, now=now)
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

    def capacity(self, channel):
        return self.db.collection('channel_capacity').document(channel)

    def waitlist(self, uid, channel, *, now=None):
        now = now or datetime.now(timezone.utc)
        self.user(uid).collection('channel_waitlist').document(channel).set(
            {'channel': channel, 'updated_at': now, 'expires_at': now + timedelta(days=30)}
        )

    def seat_state(self, uid, channel):
        """Read-only seat answer for display: None (no cap or seat available), 'seat_cap', or 'unavailable'."""
        cap = channel_policy(channel).get('seat_cap')
        if cap is None:
            return None
        capacity = self.capacity(channel)
        member = capacity.collection('members').document(uid).get().to_dict() or {}
        if member.get('link_ids'):
            return None
        row = capacity.get().to_dict() or {}
        if row.get('initialized') is not True:
            return 'unavailable'
        return 'seat_cap' if row.get('count', 0) >= cap else None

    def waitlisted(self, uid, channel):
        return self.user(uid).collection('channel_waitlist').document(channel).get().exists

    def check_capacity(self, uid, channel, *, now=None):
        state = self.seat_state(uid, channel)
        if state == 'unavailable':
            raise PermissionError('Seat counter needs reconciliation')
        if state == 'seat_cap':
            self.waitlist(uid, channel, now=now)
            raise SeatFull()

    def assert_link_capacity(self, message, link):
        if channel_policy(message.channel).get('seat_cap') is None:
            return
        capacity = self.capacity(message.channel)
        row = capacity.get().to_dict() or {}
        member = capacity.collection('members').document(link['uid']).get().to_dict() or {}
        link_id = key(message.channel, message.provider, message.external_user_id)
        if row.get('initialized') is not True or link_id not in member.get('link_ids', []):
            raise AccessDenied('seat_cap', 'iMessage seat unavailable — join the waitlist in Omi')

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
            if existing.get('cleanup_pending'):
                raise PermissionError('Identity cleanup in progress')
            if existing.get('uid') and existing['uid'] != uid:
                raise PermissionError('Identity already linked')
            cap = channel_policy(message.channel).get('seat_cap')
            capacity = member_ref = None
            link_ids, seats = [], {}
            if cap is not None:
                capacity = self.capacity(message.channel)
                member_ref = capacity.collection('members').document(uid)
                member = member_ref.get(transaction=tx).to_dict() or {}
                seats = capacity.get(transaction=tx).to_dict() or {}
                link_ids = member.get('link_ids', [])
                if not link_ids:
                    if seats.get('initialized') is not True:
                        raise PermissionError('Seat counter needs reconciliation')
                    if seats.get('count', 0) >= cap:
                        raise SeatFull()
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
            if capacity is not None and member_ref is not None:
                if identity.id not in link_ids:
                    tx.set(member_ref, {'link_ids': [*link_ids, identity.id]})
                    if not link_ids:
                        tx.set(capacity, {'count': seats.get('count', 0) + 1}, merge=True)
            tx.delete(self.user(uid).collection('channel_waitlist').document(message.channel))
            tx.set(identity, link)
            tx.set(self.user(uid).collection('channel_links').document(identity.id), link)
            tx.delete(proof_ref)
            tx.delete(self.user(uid).collection('channel_link_proofs').document(proof_ref.id))
            return link

        try:
            return run_with_transaction_contention_retry(
                self.db.transaction, apply, operation_name='messaging_transaction'
            )
        except SeatFull:
            token = proof_ref.get().to_dict()
            if token:
                self.waitlist(token['uid'], message.channel, now=now)
            raise

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
            if channel_policy(link.get('channel', 'unknown')).get('seat_cap') is not None:
                capacity = self.capacity(link.get('channel', 'unknown'))
                member_ref = capacity.collection('members').document(uid)
                member = member_ref.get(transaction=tx).to_dict() or {}
                seats = capacity.get(transaction=tx).to_dict() or {}
                link_ids = member.get('link_ids', [])
                if link_id in link_ids:
                    remaining = [value for value in link_ids if value != link_id]
                    if remaining:
                        tx.set(member_ref, {'link_ids': remaining})
                    else:
                        tx.delete(member_ref)
                        tx.set(capacity, {'count': max(0, seats.get('count', 0) - 1)}, merge=True)
            tx.update(identity, {'active': False, 'generation': str(uuid4())})
            return link

        run_with_transaction_contention_retry(self.db.transaction, revoke, operation_name='messaging_revoke')
        # Revocation precedes deletion. Workers re-check immediately before every send.
        for session in self.user(uid).collection('chat_sessions').where('channel_link_id', '==', link_id).stream():
            self.db.recursive_delete(session.reference)
        for message in self.user(uid).collection('messages').where('channel_link_id', '==', link_id).stream():
            message.reference.delete()
        self.db.recursive_delete(identity)
        mirror.delete()

    def delete_account(self, uid):
        for link in self.links(uid):
            self.unlink(uid, link['id'])
        for entry in self.user(uid).collection('channel_waitlist').stream():
            entry.reference.delete()
        for proof in self.user(uid).collection('channel_link_proofs').stream():
            self.db.collection('channel_link_proofs').document(proof.id).delete()
            proof.reference.delete()

    def enqueue(self, message):
        identity = self.identity(message.channel, message.provider, message.external_user_id)
        try:
            identity.create(
                {
                    'channel': message.channel,
                    'provider': message.provider,
                    'active': False,
                    'created_at': datetime.now(timezone.utc),
                }
            )
        except AlreadyExists:
            pass
        # Provider message ids may only be unique within a chat.
        ref = identity.collection('inbox').document(key(message.external_chat_id, message.provider_message_id))
        payload = asdict(message)
        payload['received_at'] = message.received_at.isoformat()
        head = identity.collection('inbound_chat_heads').document(key(message.external_chat_id))
        now = datetime.now(timezone.utc)
        encrypted = encryption.encrypt(json.dumps(payload), identity.id)

        @firestore.transactional
        def apply(tx):
            if ref.get(transaction=tx).exists:
                return None
            batch = read_album(tx, identity, message)
            identity_row = identity.get(transaction=tx).to_dict() or {}
            if identity_row.get('cleanup_pending'):
                raise ValueError('Identity cleanup in progress')
            prior = head.get(transaction=tx).to_dict() or {}
            tx.set(identity, {'last_inbound_at': now}, merge=True)
            if batch is not None:
                path = append_album(tx, batch, ref, payload, identity.id, now, message.channel, message.provider)
                if advances_inbound_head(message, prior):
                    tx.set(
                        head, {'provider_message_id': message.provider_message_id, 'received_at': message.received_at}
                    )
                return path
            tx.create(
                ref,
                {
                    'payload': encrypted,
                    'status': 'pending',
                    'created_at': now,
                    'channel': message.channel,
                    'provider': message.provider,
                    # Content-free: may this row replace a running reply nobody has seen yet,
                    # and in which conversation (one identity can hold several chats).
                    'supersedes': can_supersede(message),
                    'chat': key(message.external_chat_id),
                },
            )
            if advances_inbound_head(message, prior):
                tx.set(head, {'provider_message_id': message.provider_message_id, 'received_at': message.received_at})
            return ref.path

        return run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_enqueue')

    def reply_target(self, message):
        if message.callback_id:
            return message.reply_to
        head = (
            self.identity(message.channel, message.provider, message.external_user_id)
            .collection('inbound_chat_heads')
            .document(key(message.external_chat_id))
            .get()
            .to_dict()
            or {}
        )
        latest = head.get('provider_message_id')
        return (
            (message.reply_to or message.provider_message_id)
            if latest and latest != message.provider_message_id
            else None
        )

    def claim(self, path, *, now=None):
        result = self._claim(path, take_head=False, now=now)
        return result[1] if result else None

    def claim_next(self, path, *, now=None):
        """A wake identifies an inbox, not necessarily the row to run."""
        return self._claim(path, take_head=True, now=now)

    def _claim(self, path, *, take_head, now=None):
        ref = self.db.document(path)
        now = now or datetime.now(timezone.utc)

        @firestore.transactional
        def apply(tx):
            # Materialize all reads before any write (Firestore transaction rule).
            rows = list(
                ref.parent.where('status', 'in', ['pending', 'running']).order_by('created_at').stream(transaction=tx)
            )
            retired, head = [], None
            for candidate in rows:
                row = candidate.to_dict()
                if row.get('fifo_settled_at'):
                    continue
                age = _age(row, now, 'started_at' if row['status'] == 'running' else 'created_at')
                if row['status'] == 'running' and age >= STALE_SECONDS:
                    retired.append((candidate, 'stale_running', age))
                elif row['status'] == 'pending' and age >= PENDING_MAX_SECONDS:
                    retired.append((candidate, 'stale_pending', age))
                else:
                    head = candidate
                    break
            payload = None
            if head is not None:
                row = head.to_dict()
                if head.reference.path != path:
                    _queue_event(
                        'head_redirect' if take_head and row['status'] == 'pending' else 'non_head',
                        path,
                        _age(row, now),
                    )
                if row.get('album_ready_at', now) > now:
                    return None
                if row['status'] == 'pending' and (take_head or head.reference.path == path):
                    payload = json.loads(encryption.decrypt(row['payload'], ref.parent.parent.id))
            for candidate, reason, age in retired:
                # Ambiguous running effects must never be replayed.
                patch = {'fifo_settled_at': now, 'retired_reason': reason}
                if reason == 'stale_pending':
                    patch.update(status='expired', retired_at=now)
                tx.update(candidate.reference, patch)
                _queue_event(reason, candidate.reference.path, age)
            if payload is not None and head is not None:
                claim_patch: dict[str, Any] = {'status': 'running', 'started_at': now}
                if payload.get('media_group_id'):
                    claim_patch['album_appendable'] = True  # Only a generation-aware worker opts in.
                tx.update(head.reference, claim_patch)
                return head.reference.path, payload
            return None

        return run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_transaction')

    def seal_album(self, path, attachment_count):
        return seal_album(self.db, path, attachment_count, stale_seconds=STALE_SECONDS)

    def assert_running(self, path):
        row = self.db.document(path).get().to_dict() or {}
        if (
            row.get('status') != 'running'
            or row.get('fifo_settled_at')
            or _age(row, datetime.now(timezone.utc), 'started_at') >= STALE_SECONDS
        ):
            raise PermissionError('Inbox turn expired')

    def complete(self, path):
        # Content-free dedup tombstone survives retries; unlink removes its parent.
        self.db.document(path).update(
            {'status': 'done', 'payload': firestore.DELETE_FIELD, 'done_at': datetime.now(timezone.utc)}
        )

    def settle(self, path):
        # Retain evidence and prevent replay; only fully unwound workers may
        # mark their running head as no longer blocking newer admitted turns.
        ref = self.db.document(path)

        @firestore.transactional
        def apply(tx):
            row = ref.get(transaction=tx).to_dict() or {}
            if row.get('status') == 'running':
                tx.update(ref, {'fifo_settled_at': datetime.now(timezone.utc)})

        run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_transaction')

    def acquire(self, uid, surface, *, now=None):
        ref = self.user(uid).collection('channel_turn_leases').document(key(surface))
        token = str(uuid4())
        now = now or datetime.now(timezone.utc)

        @firestore.transactional
        def apply(tx):
            row = ref.get(transaction=tx).to_dict()
            if row:
                age = _age(row, now)
                if age < STALE_SECONDS:
                    _queue_event('lease_busy', ref.path, age)
                    return None
                _queue_event('stale_lease', ref.path, age)
            tx.set(ref, {'token': token, 'created_at': now})
            return token

        return run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_lease')

    def assert_lease(self, uid, surface, token):
        row = self.user(uid).collection('channel_turn_leases').document(key(surface)).get().to_dict()
        if not row or row['token'] != token or _age(row, datetime.now(timezone.utc)) >= STALE_SECONDS:
            raise PermissionError('Lost surface lease')

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
            channel_events_migrated=True,
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
        if row.get('current_session_id'):
            row = ref.parent.document(row['current_session_id']).get().to_dict()
            if not row or row.get('channel_link_id') != key(
                message.channel, message.provider, message.external_user_id
            ):
                raise PermissionError('Surface session removed')
        return row

    def events(self, uid, session_id, limit=40):
        """Bounded awareness tail; model chat context is owned by chat_db."""
        self.migrate_event_fences(uid, session_id)
        ref = self.user(uid).collection('chat_sessions').document(session_id)
        rows = list(
            ref.collection('channel_events')
            .order_by('sequence', direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [json.loads(encryption.decrypt(d.to_dict()['payload'], uid)) for d in reversed(rows)]

    def migrate_event_fences(self, uid, session_id):
        """One-time legacy fence migration before pruning. No message history is rewritten."""
        ref = self.user(uid).collection('chat_sessions').document(session_id)
        session = ref.get().to_dict() or {}
        if session.get('channel_events_migrated'):
            return
        rows = ref.collection('channel_events').order_by('__name__').stream()
        sequence = 0
        for document in rows:
            sequence += 1
            event = json.loads(encryption.decrypt(document.to_dict()['payload'], uid))
            fence = ref.collection('channel_event_fences').document(key(event['id']))

            @firestore.transactional
            def apply(tx):
                current = ref.get(transaction=tx).to_dict()
                if not current:
                    raise PermissionError('Session removed')
                self.assert_session_link(tx, uid, current)
                tx.set(fence, {'created_at': datetime.now(timezone.utc)})
                tx.update(document.reference, {'sequence': sequence})

            run_with_transaction_contention_retry(
                self.db.transaction, apply, operation_name='messaging_fence_migration'
            )
        ref.update({'channel_events_migrated': True, 'channel_event_sequence': sequence})

    def has_event(self, uid, session_id, event_ids):
        self.migrate_event_fences(uid, session_id)
        ref = self.user(uid).collection('chat_sessions').document(session_id)
        return any(ref.collection('channel_event_fences').document(key(value)).get().exists for value in event_ids)

    def append_event(self, uid, session_id, event):
        self.migrate_event_fences(uid, session_id)
        ref = self.user(uid).collection('chat_sessions').document(session_id)
        fence = ref.collection('channel_event_fences').document(key(event['id']))
        encoded = json.dumps(event)
        # This log is awareness, not authoritative message storage. Bound huge answers too.
        if len(encoded.encode()) > 12000:
            event = dict(event, content=event.get('content', '')[:2000] + '…')
            encoded = json.dumps(event)
        payload = {'payload': encryption.encrypt(encoded, uid)}

        @firestore.transactional
        def apply(tx):
            session = ref.get(transaction=tx).to_dict()
            exists = fence.get(transaction=tx).exists
            if not session:
                raise PermissionError('Session removed')
            if exists:
                return
            self.assert_session_link(tx, uid, session)
            sequence = session.get('channel_event_sequence', 0) + 1
            # z sorts after the legacy numeric document IDs.
            tx.create(ref.collection('channel_events').document(f'z{sequence:012d}'), dict(payload, sequence=sequence))
            tx.create(fence, {'created_at': datetime.now(timezone.utc)})
            tx.update(ref, {'channel_event_sequence': sequence, 'channel_event_watermark': event.get('at', '')})
            return sequence

        sequence = run_with_transaction_contention_retry(
            self.db.transaction, apply, operation_name='messaging_transaction'
        )
        if sequence is None:
            return
        # Keep 40 events. Delete in bounded batches; repeated turns finish legacy compaction.
        old = ref.collection('channel_events').where('sequence', '<=', sequence - 40).limit(200)
        batch = self.db.batch()
        for row in old.stream():
            batch.delete(row.reference)
        batch.commit()

    def reset_session(self, uid, message, link):
        surface = 'channel:' + key(message.channel, message.external_chat_id)
        ref = self.user(uid).collection('chat_sessions').document(key(surface))
        archive = self.user(uid).collection('chat_sessions').document(uuid4().hex)

        @firestore.transactional
        def apply(tx):
            previous = ref.get(transaction=tx).to_dict()
            if not previous:
                raise PermissionError('Session removed')
            self.assert_session_link(tx, uid, previous)
            fresh = dict(
                previous,
                id=archive.id,
                channel_event_sequence=0,
                channel_event_watermark='',
                channel_events_migrated=True,
                message_ids=[],
                file_ids=[],
                created_at=datetime.now(timezone.utc),
            )
            fresh.pop('current_session_id', None)
            fresh.pop('shaped_context', None)
            fresh.pop('shaped_context_revision', None)
            tx.create(archive, fresh)
            tx.update(ref, {'current_session_id': archive.id})
            return fresh

        return run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_new_session')

    def notice_allowed(self, message, reason, window=3600):
        ref = self.identity(message.channel, message.provider, message.external_user_id)
        now = datetime.now(timezone.utc)
        field = 'notice_' + reason

        @firestore.transactional
        def apply(tx):
            row = ref.get(transaction=tx).to_dict() or {}
            last = row.get(field)
            if last and (now - last).total_seconds() < window:
                return False
            tx.set(ref, {field: now}, merge=True)
            return True

        return run_with_transaction_contention_retry(self.db.transaction, apply, operation_name='messaging_notice')

    def claim_expired(self, channel, provider, limit=20):
        rows = (
            self.db.collection_group('inbox')
            .where('status', '==', 'expired')
            .where('channel', '==', channel)
            .where('provider', '==', provider)
            .limit(limit)
        )
        claimed = []
        for candidate in rows.stream():

            @firestore.transactional
            def apply(tx):
                row = candidate.reference.get(transaction=tx).to_dict() or {}
                if row.get('status') != 'expired':
                    return None
                tx.update(
                    candidate.reference,
                    {'status': 'done', 'payload': firestore.DELETE_FIELD, 'done_at': datetime.now(timezone.utc)},
                )
                return json.loads(encryption.decrypt(row['payload'], candidate.reference.parent.parent.id))

            payload = run_with_transaction_contention_retry(
                self.db.transaction, apply, operation_name='messaging_expiry'
            )
            if payload:
                claimed.append(payload)
        return claimed

    def retry(self, path):
        self.db.document(path).update({'status': 'pending', 'album_appendable': firestore.DELETE_FIELD})

    def superseding_pending(self, path):
        """True when a newer user message is waiting behind the running row at ``path``.

        Uses the same status/created_at query as :meth:`pending` (no new index) and
        reads only content-free fields.
        """
        ref = self.db.document(path)
        chat = (ref.get(['chat']).to_dict() or {}).get('chat')
        if not chat:
            return False  # a row from before this field never gets replaced
        rows = (
            ref.parent.where('status', '==', 'pending')
            .order_by('created_at')
            .limit(10)
            .select(['supersedes', 'chat'])
            .stream()
        )
        for row in rows:
            fields = row.to_dict() or {}
            if row.reference.path != path and fields.get('supersedes') and fields.get('chat') == chat:
                return True
        return False

    def pending(self, message):
        """Recovery seam: Stage B's dispatcher periodically scans its owned identities."""
        return [
            d.reference.path
            for d in self.identity(message.channel, message.provider, message.external_user_id)
            .collection('inbox')
            .where('status', '==', 'pending')
            .limit(100)
            .order_by('created_at')
            .stream()
        ]

    def assert_notice_link(self, message, link):
        @firestore.transactional
        def check(tx):
            self.assert_session_link(
                tx,
                link['uid'],
                {
                    'channel_link_id': key(message.channel, message.provider, message.external_user_id),
                    'link_generation': link['generation'],
                },
            )

        run_with_transaction_contention_retry(self.db.transaction, check, operation_name='messaging_notice_guard')

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
        return user

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

    def prepare_launch(self, *, now=None):
        """One-time content-free metadata backfill; run only with admissions disabled."""
        from config.messaging import channel_enabled

        if any(channel_enabled(channel) for channel in ('telegram', 'imessage')):
            raise ValueError('Disable messaging admission before preparing launch')
        now = now or datetime.now(timezone.utc)
        members = {}
        count = 0
        for identity in self.db.collection('channel_identities').stream():
            row = identity.to_dict()
            if not row.get('last_inbound_at'):
                identity.reference.update({'last_inbound_at': row.get('linked_at', now)})
            if row.get('active') and row.get('channel') == 'imessage' and row.get('uid'):
                members.setdefault(row['uid'], []).append(identity.id)
            # One-time scan only; steady-state recovery never scans completed inboxes.
            for inbox in identity.reference.collection('inbox').stream():
                job = inbox.to_dict()
                patch = {'channel': row.get('channel'), 'provider': row.get('provider')}
                if job.get('status') == 'done' and not job.get('done_at'):
                    patch['done_at'] = job.get('created_at', now)
                inbox.reference.update(patch)
                count += 1
        capacity = self.capacity('imessage')
        for prior in capacity.collection('members').stream():
            prior.reference.delete()
        for uid, link_ids in members.items():
            capacity.collection('members').document(uid).set({'link_ids': link_ids})
        capacity.set({'initialized': True, 'count': len(members)})
        return {'seats': len(members), 'inbox_metadata': count}

    def cleanup(self, *, now=None, limit=100, retention_days=30):
        """Bounded hourly maintenance. Never sends messages or touches linked identities."""
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=retention_days)
        counts = {'proofs': 0, 'identities': 0, 'inbox': 0, 'waitlist': 0}
        for proof in self.db.collection('channel_link_proofs').where('expires_at', '<=', now).limit(limit).stream():
            row = proof.to_dict()
            batch = self.db.batch()
            batch.delete(proof.reference)
            batch.delete(self.user(row['uid']).collection('channel_link_proofs').document(proof.id))
            batch.commit()
            counts['proofs'] += 1
        for identity in (
            self.db.collection('channel_identities')
            .where('active', '==', False)
            .where('last_inbound_at', '<=', cutoff)
            .limit(limit)
            .stream()
        ):

            @firestore.transactional
            def revoke(tx):
                row = identity.reference.get(transaction=tx).to_dict() or {}
                if row.get('active') or row.get('uid') or row.get('last_inbound_at', now) > cutoff:
                    return False
                # Unknown senders can also have ambiguous provider delivery. Never
                # erase their running reconciliation evidence through a parent purge.
                running = identity.reference.collection('inbox').where('status', '==', 'running').limit(1)
                if next(running.stream(transaction=tx), None) is not None:
                    return False
                tx.update(identity.reference, {'cleanup_pending': True})
                return True

            if run_with_transaction_contention_retry(self.db.transaction, revoke, operation_name='messaging_cleanup'):
                self.db.recursive_delete(identity.reference)
                counts['identities'] += 1
        for inbox in (
            self.db.collection_group('inbox')
            .where('status', '==', 'done')
            .where('done_at', '<=', cutoff)
            .limit(limit)
            .stream()
        ):
            if not inbox.reference.path.startswith('channel_identities/'):
                continue
            inbox.reference.delete()
            counts['inbox'] += 1
        for entry in self.db.collection_group('channel_waitlist').where('expires_at', '<=', now).limit(limit).stream():
            entry.reference.delete()
            counts['waitlist'] += 1
        return counts

    def pending_jobs(self, channel, provider, limit=100):
        query = (
            self.db.collection_group('inbox')
            .where('status', '==', 'pending')
            .where('channel', '==', channel)
            .where('provider', '==', provider)
            .order_by('created_at')
            .limit(limit)
        )
        return [doc.reference.path for doc in query.stream()]


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
