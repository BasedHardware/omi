"""In-memory service double, not a substitute for Firestore transaction integration tests."""

import copy
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

from utils.messaging.identity import key
from database.messaging import STALE_SECONDS, PENDING_MAX_SECONDS


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
            self.jobs[path] = dict(
                payload=payload,
                status='pending',
                created_at=datetime.now(timezone.utc),
                identity=(message.channel, message.provider, message.external_user_id),
            )
        return path

    def claim(self, path, *, now=None):
        result = self._claim(path, False, now)
        return result[1] if result else None

    def claim_next(self, path, *, now=None):
        return self._claim(path, True, now)

    def _claim(self, path, take_head, now):
        now = now or datetime.now(timezone.utc)
        identity = self.jobs[path].get('identity')
        with self.lock:
            for candidate, row in sorted(self.jobs.items(), key=lambda pair: pair[1].get('created_at', now)):
                if (
                    row.get('identity') != identity
                    or row['status'] not in ('pending', 'running')
                    or row.get('fifo_settled_at')
                ):
                    continue
                age = (now - (row.get('started_at') or row['created_at'])).total_seconds()
                if row['status'] == 'running' and age >= STALE_SECONDS:
                    row['fifo_settled_at'] = now
                    continue
                if row['status'] == 'pending' and (now - row['created_at']).total_seconds() >= PENDING_MAX_SECONDS:
                    row.update(status='done', fifo_settled_at=now)
                    row.pop('payload', None)
                    continue
                if row['status'] == 'running' or (not take_head and candidate != path):
                    return None
                row.update(status='running', started_at=now)
                return candidate, copy.deepcopy(row['payload'])
        return None

    def assert_running(self, path):
        row = self.jobs[path]
        if row['status'] != 'running' or row.get('fifo_settled_at'):
            raise PermissionError('Inbox turn expired')

    def assert_lease(self, uid, surface, token):
        if self.leases.get((uid, surface)) != token:
            raise PermissionError('Lost surface lease')

    def retry(self, path):
        self.jobs[path]['status'] = 'pending'

    def complete(self, path):
        self.jobs[path].update(status='done')
        self.jobs[path].pop('payload', None)

    def settle(self, path):
        if self.jobs[path]['status'] == 'running':
            self.jobs[path]['fifo_settled_at'] = datetime.now(timezone.utc)

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

    def pending(self, message):
        return [
            path
            for path, row in sorted(
                self.jobs.items(), key=lambda item: item[1].get('created_at', datetime.min.replace(tzinfo=timezone.utc))
            )
            if row['status'] == 'pending'
        ]
