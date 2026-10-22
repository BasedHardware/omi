"""In-memory service double, not a substitute for Firestore transaction integration tests."""

import copy
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

from utils.messaging.identity import key, advances_inbound_head
from database.messaging import STALE_SECONDS, PENDING_MAX_SECONDS, can_supersede


class MemoryStore:
    def __init__(self):
        self.proofs, self.identities, self.jobs, self.sessions, self.logs, self.leases = {}, {}, {}, {}, {}, {}
        self.chat_heads = {}
        self.album_parts = set()
        self.notices = {}
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
            if path in self.jobs or path in self.album_parts:
                return None
            payload = asdict(message)
            payload['received_at'] = message.received_at.isoformat()
            album_path = None
            sequence = total = 0
            if message.media_group_id:
                from utils.messaging.albums import merge_album, album_ready_at

                album_path = key(
                    message.channel,
                    message.provider,
                    message.external_user_id,
                    message.external_chat_id,
                    'album:' + message.media_group_id,
                )
                root = self.jobs.get(album_path)
                sequence = (root or {}).get('album_tail', 0)
                path = album_path if sequence == 0 else key(album_path, str(sequence))
                row = self.jobs.get(path)
                if row and (
                    row['status'] not in ('pending', 'running')
                    or (row['status'] == 'running' and not row.get('album_appendable'))
                    or row.get('generation_started_at')
                    or row.get('fifo_settled_at')
                ):
                    sequence += 1
                    path = key(album_path, str(sequence))
                    row = None
                total = (root or {}).get('album_part_count', 0) + len(payload['attachments'])
                if total > 10:
                    raise ValueError('Album contains too many attachments')
                self.album_parts.add(
                    key(
                        message.channel,
                        message.provider,
                        message.external_user_id,
                        message.external_chat_id,
                        message.provider_message_id,
                    )
                )
                payload = merge_album(row['payload'] if row else None, payload)
                ready = album_ready_at(row, datetime.now(timezone.utc))
            else:
                row, ready = None, None
            created_at = row['created_at'] if row else datetime.now(timezone.utc)
            self.jobs.setdefault(path, {}).update(
                payload=payload,
                status=row['status'] if row else 'pending',
                created_at=created_at,
                album_ready_at=ready,
                identity=(message.channel, message.provider, message.external_user_id),
                supersedes=row.get('supersedes', False) if row else can_supersede(message),
                chat=key(message.external_chat_id),
            )
            if album_path is not None:
                self.jobs[album_path].update(album_tail=sequence, album_part_count=total)
            chat = (message.channel, message.provider, message.external_user_id, message.external_chat_id)
            prior = self.chat_heads.get(chat)
            previous = (
                {'received_at': prior.received_at, 'provider_message_id': prior.provider_message_id} if prior else {}
            )
            if advances_inbound_head(message, previous):
                self.chat_heads[chat] = message
        return path

    def reply_target(self, message):
        if message.callback_id:
            return message.reply_to
        latest = self.chat_heads.get(
            (message.channel, message.provider, message.external_user_id, message.external_chat_id)
        )
        return (
            (message.reply_to or message.provider_message_id)
            if latest and latest.provider_message_id != message.provider_message_id
            else None
        )

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
                if row.get('album_ready_at') and row['album_ready_at'] > now:
                    return None
                row.update(
                    status='running', started_at=now, album_appendable=bool(row['payload'].get('media_group_id'))
                )
                return candidate, copy.deepcopy(row['payload'])
        return None

    def seal_album(self, path, attachment_count):
        with self.lock:
            self.assert_running(path)
            row = self.jobs[path]
            if len(row['payload']['attachments']) != attachment_count:
                return copy.deepcopy(row['payload'])
            row['generation_started_at'] = datetime.now(timezone.utc)
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
        self.jobs[path].pop('album_appendable', None)

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

    def assert_link_capacity(self, message, link):
        pass

    def assert_notice_link(self, message, link):
        current = self.lookup(message)
        if not current or not current.get('active') or current.get('generation') != link['generation']:
            raise PermissionError('Link revoked')

    def has_event(self, uid, session, event_ids):
        return any(e['id'] in event_ids for e in self.events(uid, session))

    def notice_allowed(self, message, reason, window=3600):
        identity = (message.channel, message.external_user_id, reason)
        now = datetime.now(timezone.utc)
        with self.lock:
            if identity in self.notices and (now - self.notices[identity]).total_seconds() < window:
                return False
            self.notices[identity] = now
            return True

    def reset_session(self, uid, message, link):
        surface = 'channel:' + key(message.channel, message.external_chat_id)
        self.sessions[(uid, surface)] = {'id': uuid4().hex, 'surface': surface}
        return self.sessions[(uid, surface)]

    def claim_expired(self, channel, provider, limit=20):
        return []

    def persist_message(self, uid, document, session_id):
        return document

    def proof_owner(self, proof):
        row = self.proofs.get(proof)
        if not row:
            raise PermissionError('Invalid proof')
        return row['uid']

    def superseding_pending(self, path):
        with self.lock:
            identity, chat = self.jobs[path].get('identity'), self.jobs[path].get('chat')
            if not chat:
                return False  # a row from before the field is never replaced
            return any(
                other != path
                and row['status'] == 'pending'
                and row.get('identity') == identity
                and row.get('chat') == chat
                and row.get('supersedes')
                for other, row in self.jobs.items()
            )

    def pending(self, message):
        return [
            path
            for path, row in sorted(
                self.jobs.items(), key=lambda item: item[1].get('created_at', datetime.min.replace(tzinfo=timezone.utc))
            )
            if row['status'] == 'pending'
        ]
