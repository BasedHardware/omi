"""Firestore inbox, recipient outbox and attempt receipts."""

from datetime import timedelta
import re

from google.api_core.exceptions import Aborted
from google.cloud import firestore

from .publisher import MAX_EVENT_AGE, digest

MAX_ATTEMPTS = 3
ATTEMPT_LEASE = timedelta(seconds=90)
RETRY_DELAY = timedelta(minutes=1)
WAKE_WINDOW = timedelta(hours=1)
WAKE_LIMIT = 6
DRAIN_LIMIT = 4


def due_deliveries(db, now):
    return (
        db.collection('pager_deliveries')
        .where(filter=firestore.FieldFilter('next_at', '<=', now))
        .order_by('next_at')
        .limit(DRAIN_LIMIT)
        .stream(timeout=5)
    )


class TransactionRetriesExhausted(RuntimeError):
    """Firestore abandoned a write transaction after its SDK retry budget."""


class Store:
    def __init__(self, db, count_operation=lambda _: None):
        self.db = db
        self.count_operation = count_operation

    def _transaction(self, commit):
        try:
            return commit(self.db.transaction())
        except ValueError as error:
            # Firestore 2.20.0 wraps exhausted commit aborts in this ValueError.
            if isinstance(error.__cause__, Aborted) and re.fullmatch(
                r'Failed to commit transaction in [0-9]+ attempts\.', str(error)
            ):
                raise TransactionRetriesExhausted() from error
            raise

    def read(self, ref, transaction):
        self.count_operation('read')
        return ref.get(transaction=transaction, timeout=5).to_dict()

    def write(self, transaction, operation, ref, values):
        self.count_operation('write')
        getattr(transaction, operation)(ref, values)

    def admit(self, event, now):
        events = self.db.collection('pager_events')
        event_ref = events.document(event.event_id)
        delivery_ref = self.delivery_ref(event.delivery_id)

        @firestore.transactional
        def commit(transaction):
            previous = self.read(event_ref, transaction)
            if previous is not None:
                return 'duplicate'

            delivery = self.read(delivery_ref, transaction)
            route = event.route
            disposition = 'queued'
            state = 'queued'
            next_at = now
            if event.status == 'resolved':
                disposition, state, next_at = 'quiet_recovery', 'resolved', None
            elif delivery is not None:
                disposition, state, next_at = 'suppressed_resolved', 'resolved', None
            elif event.starts_at + MAX_EVENT_AGE <= now:
                disposition, state, next_at = 'suppressed_stale', 'expired', None

            self.write(
                transaction,
                'create',
                event_ref,
                {
                    'episode_id': event.episode_id,
                    'delivery_id': event.delivery_id,
                    'publisher': route.publisher,
                    'rule_uid': route.uid,
                    'target': route.target,
                    'route': route.route_id,
                    'recipient': route.recipient,
                    'channel': route.channel,
                    'fingerprint': event.fingerprint,
                    'status': event.status,
                    'starts_at': event.starts_at,
                    'ends_at': event.ends_at,
                    'received_at': now,
                    'disposition': disposition,
                },
            )
            if delivery is None:
                self.write(
                    transaction,
                    'create',
                    delivery_ref,
                    {
                        'episode_id': event.episode_id,
                        'route': route.route_id,
                        'recipient': route.recipient,
                        'channel': route.channel,
                        'state': state,
                        'next_at': next_at,
                        'expires_at': event.starts_at + MAX_EVENT_AGE,
                        'resolved_at': event.ends_at,
                        'attempts': [],
                    },
                )
            elif event.status == 'resolved':
                changes = {'resolved_at': event.ends_at}
                if delivery['state'] in ('queued', 'retry'):
                    changes.update(state='resolved', next_at=None)
                self.write(transaction, 'update', delivery_ref, changes)
            return disposition

        return self._transaction(commit)

    def delivery_ref(self, delivery_id):
        return self.db.collection('pager_deliveries').document(delivery_id)

    def due(self, now):
        self.count_operation('query')
        for snapshot in due_deliveries(self.db, now):
            self.count_operation('query_result')
            yield snapshot.id

    def claim(self, delivery_id, now):
        ref = self.delivery_ref(delivery_id)

        @firestore.transactional
        def commit(transaction):
            delivery = self.read(ref, transaction)
            if not delivery or delivery['next_at'] is None or delivery['next_at'] > now:
                return None
            attempts = delivery['attempts']
            if delivery['state'] == 'sending':
                # A process may have sent before dying. Never replay this attempt.
                attempts[-1].update(outcome='unknown', reason='lease_expired', completed_at=now)
                self.write(transaction, 'update', ref, {'state': 'unknown', 'next_at': None, 'attempts': attempts})
                return None
            if delivery['resolved_at'] is not None or delivery['expires_at'] <= now:
                state = 'resolved' if delivery['resolved_at'] is not None else 'expired'
                self.write(transaction, 'update', ref, {'state': state, 'next_at': None})
                return None

            if not attempts:
                cap_ref = self.db.collection('pager_recipient_limits').document(digest(delivery['recipient']))
                cap = self.read(cap_ref, transaction) or {}
                reservations = [time for time in cap.get('reservations', []) if time > now - WAKE_WINDOW]
                if len(reservations) >= WAKE_LIMIT:
                    self.write(transaction, 'update', ref, {'state': 'suppressed_cap', 'next_at': None})
                    return None
                self.write(transaction, 'set', cap_ref, {'reservations': reservations + [now]})

            attempt = len(attempts) + 1
            attempts.append({'number': attempt, 'claimed_at': now, 'outcome': 'sending'})
            self.write(
                transaction,
                'update',
                ref,
                {'state': 'sending', 'next_at': now + ATTEMPT_LEASE, 'attempts': attempts},
            )
            return attempt, delivery['route'], delivery['recipient'], delivery['channel']

        return self._transaction(commit)

    def finish(self, delivery_id, number, outcome, reason, now):
        ref = self.delivery_ref(delivery_id)

        @firestore.transactional
        def commit(transaction):
            delivery = self.read(ref, transaction)
            attempts = delivery['attempts']
            if delivery['state'] != 'sending' or attempts[-1]['number'] != number:
                return
            attempts[-1].update(outcome=outcome, reason=reason, completed_at=now)
            next_at = None
            if outcome == 'retryable':
                state = 'failed'
                retry_at = now + RETRY_DELAY * number
                if delivery['resolved_at'] is not None:
                    state = 'resolved'
                elif number < MAX_ATTEMPTS and retry_at < delivery['expires_at']:
                    state, next_at = 'retry', retry_at
            else:
                state = outcome
            self.write(transaction, 'update', ref, {'state': state, 'next_at': next_at, 'attempts': attempts})

        self._transaction(commit)

    def acknowledge(self, delivery_id, now):
        ref = self.delivery_ref(delivery_id)

        @firestore.transactional
        def commit(transaction):
            delivery = self.read(ref, transaction)
            if not delivery or delivery['state'] not in ('provider_accepted', 'unknown'):
                return False
            if 'acknowledgement' not in delivery:
                self.write(
                    transaction,
                    'update',
                    ref,
                    {'acknowledgement': {'kind': 'handset_witness', 'recorded_by': 'paging-operator', 'at': now}},
                )
            return True

        return self._transaction(commit)
