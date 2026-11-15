"""Dedicated, content-free speaker-pass obligations; Cloud Tasks are only wakes."""

import hashlib
import random
import uuid

from database.outbox_cas import mutate

MAX_ATTEMPTS = 4
LEASE_SECONDS = 900
DIRECT_LEASE_SECONDS = 3600
REPAIR_SECONDS = 120
COUNTER_SHARDS = 16


def backoff(attempt):
    return random.uniform(0.5, 1.5) * min(240, 30 * 2**attempt)


def obligation_key(uid, conversation_id, scope_key):
    return hashlib.sha256(f'{uid}\0{conversation_id}\0{scope_key}'.encode()).hexdigest()


def terminal_plan(old, counts, token):
    """One atomic receipt/counter plan; no process-local metric side effects."""
    if not old or old['token'] != token or not old.get('outcome') or not old.get('terminal_pending'):
        return None
    from utils.observability.reasons import BatchFinalPassOutcome, ReasonFamily, reason_label

    row, counts = dict(old), dict(counts)
    for field in ('terminal_pending', 'repair_after', 'due_at'):
        row.pop(field, None)
    if old['outcome'] != 'skipped_ineligible':
        outcome = (
            'success'
            if old['outcome'] == 'success'
            else reason_label(ReasonFamily.BATCH_FINAL_PASS, old['outcome'], BatchFinalPassOutcome)
        )
        counts[outcome] = counts.get(outcome, 0) + 1
    return row, counts


def claim_plan(old, token, *, now, direct=False):
    if not old or old['token'] != token or old['lease_until'] > now:
        return old, ('stale', None)
    if old['outcome']:
        return old, ('terminal', old) if old.get('terminal_pending') else ('stale', None)
    if not direct and old['due_at'] > now:
        row = {**old, 'token': uuid.uuid4().hex}
        return row, ('early', row)
    if old['attempts'] >= MAX_ATTEMPTS:
        row = {
            **old,
            'outcome': 'skipped_retry_exhausted',
            'lease': None,
            'lease_until': 0,
            'terminal_pending': True,
            'repair_after': now + REPAIR_SECONDS,
        }
        for field in ('due_at', 'uid', 'conversation_id', 'dispatch'):
            row.pop(field, None)
        return row, ('exhausted', row)
    row = {
        **old,
        'attempts': old['attempts'] + 1,
        'lease': uuid.uuid4().hex,
        'lease_until': now + (DIRECT_LEASE_SECONDS if direct else LEASE_SECONDS),
        'repair_after': now + (DIRECT_LEASE_SECONDS if direct else LEASE_SECONDS),
    }
    return row, ('claimed', row)


class FinalPassRetries:
    def __init__(self, client=None):
        self.client = client

    def _client(self):
        if self.client is not None:
            return self.client
        from database._client import get_data_plane_firestore_client

        return get_data_plane_firestore_client()

    def _collection(self):
        from utils.sync.stage import current_stage

        return self._client().collection(f'batch_pipeline_{current_stage()}_speaker_final_pass_outbox')

    def _mutate(self, key, operation):
        return mutate(self._collection().document(key), operation)

    def enqueue(self, uid, conversation_id, scope_key, dispatch, *, now):
        key = obligation_key(uid, conversation_id, scope_key)

        def create(old):
            if old:
                return old, (old, False)  # Closed receipts never reopen or reset the cap.
            due = now + backoff(0)
            row = dict(
                uid=uid,
                conversation_id=conversation_id,
                scope_key=scope_key,
                dispatch=dispatch,
                due_at=due,
                repair_after=due + REPAIR_SECONDS,
                attempts=0,
                token=uuid.uuid4().hex,
                lease_until=0,
                lease=None,
                outcome=None,
            )
            return row, (row, True)

        row, created = self._mutate(key, create)
        return key, row, created

    def start_direct(self, uid, conversation_id, scope_key, dispatch, *, now):
        key = obligation_key(uid, conversation_id, scope_key)

        def start(old):
            if old:
                return claim_plan(old, old['token'], now=now, direct=True)
            # The first synchronous attempt does not spend one of the four
            # subsequent claims. Hold custody through canonical persistence.
            row = dict(
                uid=uid,
                conversation_id=conversation_id,
                scope_key=scope_key,
                dispatch=dispatch,
                due_at=now,
                repair_after=now + DIRECT_LEASE_SECONDS,
                attempts=0,
                token=uuid.uuid4().hex,
                lease_until=now + DIRECT_LEASE_SECONDS,
                lease=uuid.uuid4().hex,
                outcome=None,
            )
            return row, ('claimed', row)

        state, row = self._mutate(key, start)
        return key, state, row

    def claim(self, key, token, *, now):
        return self._mutate(key, lambda old: claim_plan(old, token, now=now))

    def settle(self, key, claim, outcome, *, now):
        def finish(old):
            if not old or old['outcome'] or old['lease'] != claim['lease'] or old['token'] != claim['token']:
                return old, None
            retry = outcome.startswith('deferred_')
            terminal = outcome
            if retry and old['attempts'] >= MAX_ATTEMPTS:
                terminal = 'skipped_slot_exhausted' if outcome == 'deferred_slot_busy' else 'skipped_retry_exhausted'
                retry = False
            row = {**old, 'lease': None, 'lease_until': 0}
            if retry:
                due = now + backoff(old['attempts'])
                row.update(token=uuid.uuid4().hex, due_at=due, repair_after=due + REPAIR_SECONDS)
            else:
                # Keep a content-free reporting obligation until a fenced
                # reporter takes it. A lost settlement reply must not strand it.
                row.update(outcome=terminal, terminal_pending=True, repair_after=now + REPAIR_SECONDS)
                for field in ('due_at', 'uid', 'conversation_id', 'dispatch'):
                    row.pop(field, None)
            return row, row

        return self._mutate(key, finish)

    def _counter_collection(self):
        return self._client().collection(self._collection().id + '_terminal_counters')

    def take_terminal(self, key, token):
        # The metric and its idempotency receipt commit together. An ambiguous
        # reply can lose a log line, but never the durable terminal count.
        from google.cloud import firestore

        receipt = self._collection().document(key)
        counter = self._counter_collection().document(str(int(key[:2], 16) % COUNTER_SHARDS))

        @firestore.transactional
        def report(transaction):
            old = receipt.get(transaction=transaction, retry=None, timeout=3).to_dict()
            if not old or old['token'] != token or not old.get('terminal_pending'):
                return False
            counts = counter.get(transaction=transaction, retry=None, timeout=3).to_dict() or {}
            plan = terminal_plan(old, counts, token)
            if plan is None:
                return False
            row, counts = plan
            transaction.set(receipt, row)
            transaction.set(counter, counts)
            return True

        return report(self._client().transaction(max_attempts=1))

    def terminal_counts(self):
        # Fixed-size read, even after all completed receipts leave the repair
        # index. Scrapes never perform Firestore IO.
        references = [self._counter_collection().document(str(i)) for i in range(COUNTER_SHARDS)]
        counts = {
            snapshot.id: snapshot.to_dict() or {}
            for snapshot in self._client().get_all(references, retry=None, timeout=3)
        }
        if set(counts) != set(map(str, range(COUNTER_SHARDS))):
            raise ValueError('retry_counter_snapshot_incomplete')
        return counts

    def due(self, *, now, limit=100):
        # A single-field range uses Firestore's automatic index. Reported
        # terminal receipts have no repair_after and cannot pin discovery.
        return list(self._collection().where('repair_after', '<=', now).order_by('repair_after').limit(limit).stream())

    def repair(self, key, token, *, now, wake_exists=False):
        def rearm(old):
            if (
                not old
                or (old['outcome'] and not old.get('terminal_pending'))
                or old['token'] != token
                or old['repair_after'] > now
            ):
                return old, None
            if old['lease_until'] > now or (wake_exists and not old['lease']):
                return {**old, 'repair_after': max(now + REPAIR_SECONDS, old['lease_until'])}, None
            # Rotate after a lost wake or expired lease. Attempts are never reset.
            due = now + backoff(0)
            row = {
                **old,
                'token': uuid.uuid4().hex,
                'lease': None,
                'lease_until': 0,
                'due_at': due,
                'repair_after': due + REPAIR_SECONDS,
            }
            return row, row

        return self._mutate(key, rearm)
