"""Dark Firestore queue authority and commit guard for every registered writer.

Imports activate nothing. A selected store explicitly binds a namespace/epoch;
direct and bulk writers share the Commit interceptor. No PG connection spans a
Firestore RPC. Unknown queue tables and stale epochs refuse rather than guess.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import re

from google.cloud.firestore_v1.types import Document, DocumentMask, Precondition, Write

from database.jobstore.authority import AuthorityRefused, Epoch

HANDOFF_COLLECTION = 'jobstore_handoffs'
QUEUE_TABLES = frozenset(
    {
        'jobs',
        'results',
        'control',
        'queues',
        'owners',
        'gpus',
        'intakes',
        'artifacts',
        'pull_claims',
        'merge_holds',
        'projections',
        'shadow_jobs',
        'coalesce_groups',
        'coalesce_sources',
        'coalesce_heads',
        'coalesce_quota',
    }
)


def handoff_ref(client, namespace, kind, key=''):
    identity = hashlib.sha256(f'{namespace}/{kind}/{key}'.encode()).hexdigest()
    return client.collection(HANDOFF_COLLECTION).document(identity)


class FirestoreAuthority:
    def __init__(self, client, ticket: Epoch):
        if (
            not re.fullmatch(r'batch_pipeline_(prod|dev|test_[a-z0-9_]{1,40})', ticket.namespace)
            or type(ticket.value) is not int
            or ticket.value < 0
        ):
            raise ValueError('explicit namespace and nonnegative epoch required')
        self.client, self.ticket = client, ticket
        self.ref = handoff_ref(client, ticket.namespace, 'authority')

    def check(self, transaction=None, *, phases=('FS_OPEN',)):
        snapshot = self.ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        if (
            data.get('namespace') != self.ticket.namespace
            or data.get('epoch') != self.ticket.value
            or data.get('state') not in phases
            or data.get('protocol') != 1
        ):
            raise AuthorityRefused('Firestore queue authority closed, unknown or stale')
        return snapshot

    @contextmanager
    def writers(self):
        from database.batch_privacy_write_fence import queue_coordinator

        token = queue_coordinator.set(self)
        try:
            yield
        finally:
            queue_coordinator.reset(token)

    def covers(self, write):
        path = write.delete or write.update.name or write.transform.document
        bits = path.split('/documents/', 1)[-1].split('/')
        if not bits[0].startswith(self.ticket.namespace + '_'):
            return False
        if len(bits) != 2:
            raise AuthorityRefused('queue subcollection writer is not inventoried')
        table = bits[0][len(self.ticket.namespace) + 1 :]
        if table not in QUEUE_TABLES:
            raise AuthorityRefused('unknown queue writer table; cutover inventory incomplete')
        return True

    def prepare(self, request):
        if not any(self.covers(write) for write in request.writes):
            return False
        snapshot = self.check()
        # Direct/CAS writers cannot join a caller's read transaction. This
        # precondition is evaluated atomically with their original writes. The
        # normal Store also reads the authority inside its mutation transaction.
        request.writes.append(
            Write(
                update=Document(name=self.ref._document_path),
                update_mask=DocumentMask(field_paths=[]),
                current_document=Precondition(update_time=snapshot.update_time),
            )
        )
        return True

    def transition(self, expected, target, transition_id):
        """FS half of the operator's resumable transition, with strict epoch CAS.

        Source/target opening still requires the PG/certificate coordinator. This
        API never opens FS from another state, so it cannot be an env rollback.
        """
        from google.cloud import firestore

        edges = {
            'FS_OPEN': 'FS_CLOSING',
            'FS_CLOSING': 'BOTH_CLOSED',
            'PG_OPEN': 'PG_CLOSING',
            'PG_CLOSING': 'BOTH_CLOSED',
        }
        if edges.get(expected) != target or not transition_id:
            raise AuthorityRefused('opening requires a verified cross-store certificate')

        @firestore.transactional
        def close(transaction):
            snapshot = self.check(transaction, phases=(expected,))
            data = snapshot.to_dict()
            transaction.update(
                self.ref, {'state': target, 'epoch': self.ticket.value + 1, 'transition_id': transition_id}
            )
            return {**data, 'state': target, 'epoch': self.ticket.value + 1, 'transition_id': transition_id}

        return close(self.client.transaction())
