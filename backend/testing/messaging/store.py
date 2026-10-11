"""In-memory service double, not a substitute for Firestore transaction integration tests."""

import copy
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

from utils.messaging.identity import key


class MemoryStore:
    def __init__(self):
        self.proofs, self.identities, self.jobs, self.sessions, self.logs, self.leases = {}, {}, {}, {}, {}, {}
        self.lock = RLock()

    def mint(self, uid, channel, provider, kind, *, now=None):
        proof = secrets.token_urlsafe(24)
        expires = (now or datetime.now(timezone.utc)) + timedelta(minutes=10)
        self.proofs[proof] = dict(uid=uid, channel=channel, provider=provider, kind=kind, expires_at=expires)
        return dict(proof=proof, kind=kind, expires_at=expires)

    def consume(self, proof, message, *, now=None):
        with self.lock:
            row = self.proofs.get(proof)
            if not row or row['expires_at'] <= (now or datetime.now(timezone.utc)):
                raise PermissionError('Invalid proof')
            if (row['channel'], row['provider']) != (message.channel, message.provider):
                raise PermissionError('Wrong audience')
            old = self.lookup(message)
            if old and old['uid'] != row['uid']:
                raise PermissionError('Already linked')
            link = dict(row, generation=str(uuid4()), active=True, visible_in_app=False)
            self.identities[(message.channel, message.provider, message.external_user_id)] = link
            del self.proofs[proof]
            return link

    def lookup(self, message):
        return self.identities.get((message.channel, message.provider, message.external_user_id))

    def enqueue(self, message):
        path = key(
            message.channel,
            message.provider,
            message.external_user_id,
            message.external_chat_id,
            message.provider_message_id,
        )
        with self.lock:
            if path in self.jobs:
                return None
            payload = asdict(message)
            payload['received_at'] = message.received_at.isoformat()
            self.jobs[path] = dict(payload=payload, status='pending')
        return path

    def claim(self, path):
        with self.lock:
            row = self.jobs[path]
            if row['status'] != 'pending':
                return None
            row['status'] = 'running'
            return copy.deepcopy(row['payload'])

    def retry(self, path):
        self.jobs[path]['status'] = 'pending'

    def complete(self, path):
        self.jobs[path] = {'status': 'done'}

    def acquire(self, uid, surface):
        with self.lock:
            if (uid, surface) in self.leases:
                return None
            token = str(uuid4())
            self.leases[(uid, surface)] = token
            return token

    def release(self, uid, surface, token):
        with self.lock:
            assert self.leases[(uid, surface)] == token
            del self.leases[(uid, surface)]

    def session(self, uid, message, link):
        surface = 'channel:' + key(message.channel, message.external_chat_id)
        return self.sessions.setdefault((uid, surface), {'id': key(surface), 'surface': surface})

    def events(self, uid, session):
        return copy.deepcopy(self.logs.get((uid, session), []))

    def append_event(self, uid, session, event):
        log = self.logs.setdefault((uid, session), [])
        if not any(e['id'] == event['id'] for e in log):
            log.append(copy.deepcopy(event))

    def persist_message(self, uid, document, session_id):
        return document

    def proof_owner(self, proof):
        row = self.proofs.get(proof)
        if not row:
            raise PermissionError('Invalid proof')
        return row['uid']
