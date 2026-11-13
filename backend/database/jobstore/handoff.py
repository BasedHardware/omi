"""Explicitly injected, dark FS -> PG -> FS custody protocol.

Callbacks are transaction bodies, never dispatchers: admission/completion join
the queue SQL transaction and projection joins the existing customer transaction.
No database connection survives an FS RPC. This module does not select a serving
backend, generate policies, upload bodies, or retire outstanding custody by TTL.
"""

from __future__ import annotations

from database.jobstore import codec
from database.jobstore.authority import AuthorityRefused, acquire, fingerprint
from database.jobstore.fs_fence import FirestoreAuthority, handoff_ref
from database.jobstore.postgres_store import jsonb
from database.privacy_fence import owner_key
from database.privacy_fence.protocol import row_dict


def bounded(value):
    if len(codec.canonical(value).encode()) > 256_000:
        raise ValueError('handoff metadata exceeds bounded envelope')
    return value


class Handoff:
    def __init__(self, pool, fence, client, ticket):
        self.pool, self.fence, self.client, self.ticket = pool, fence, client, ticket
        self.authority = FirestoreAuthority(client, ticket)

    def ref(self, kind, identity):
        return handoff_ref(self.client, self.ticket.namespace, kind, identity)

    def stage(self, transaction, identity, uid, conversation_ids, payload):
        """Join the ORIGINAL FS admission transaction, before its first write.

        The source adapter must supply only existing custody references and queue
        metadata. Acknowledgement does not grant a new retention policy. Outstanding
        intents deliberately have no automatic expiry (A9).
        """
        if not identity or len(identity.encode()) > 256:
            raise ValueError('bounded stable admission identity required')
        self.authority.check(transaction, phases=('PG_OPEN',))
        cids = sorted(set(conversation_ids))
        if len(cids) > 128 or any(not cid or '/' in cid for cid in cids):
            raise ValueError('bounded conversation targets required')
        intent = bounded(
            dict(
                namespace=self.ticket.namespace,
                epoch=self.ticket.value,
                identity=identity,
                uid=uid,
                owner_key=owner_key(uid),
                conversation_ids=cids,
                payload=payload,
            )
        )
        intent = codec.loads(codec.canonical(intent))
        digest = fingerprint(intent)
        ref = self.ref('intent', identity)
        old = ref.get(transaction=transaction).to_dict()
        if old:
            if old.get('fingerprint') != digest or old.get('intent') != intent:
                raise AuthorityRefused('admission identity reused with different intent')
            return digest
        transaction.create(ref, {'intent': intent, 'fingerprint': digest})
        return digest

    def _row(self, conn, identity):
        return row_dict(
            conn, 'SELECT * FROM queue_handoffs WHERE namespace=%s AND identity=%s', (self.ticket.namespace, identity)
        )

    def _guard(self, conn, row):
        if row is None or row['epoch'] != self.ticket.value:
            raise AuthorityRefused('unknown or stale handoff')
        admission = codec.loads(codec.canonical(row['admission']))
        self.fence.check_work_write(conn, row['owner_key'], admission)
        acquire(conn, self.ticket)

    def _required_row(self, conn, identity):
        row = self._row(conn, identity)
        if row is None:
            raise AuthorityRefused('unknown handoff')
        return row

    def deliver(self, identity, mutate):
        """Idempotent PG admission. `mutate(conn, payload, admission)` is SQL only.

        A lost PG COMMIT response leaves the FS intent intact. Replay checks the
        immutable intent and never runs its queue mutation twice.
        """
        source = self.ref('intent', identity).get().to_dict() or {}
        intent = source.get('intent', {})
        digest = source.get('fingerprint')
        if (
            not intent
            or digest != fingerprint(intent)
            or intent.get('identity') != identity
            or intent.get('namespace') != self.ticket.namespace
            or intent.get('epoch') != self.ticket.value
        ):
            raise AuthorityRefused('missing, corrupt or stale admission intent')
        saved = []

        def persist(conn, admission):
            acquire(conn, self.ticket)
            row = self._row(conn, identity)
            if row:
                if row['fingerprint'] != digest or row['owner_key'] != owner_key(intent['uid']):
                    raise AuthorityRefused('PG admission identity conflict')
                self._guard(conn, row)
                saved.append(codec.loads(codec.canonical(row['admission'])))
                return
            conn.execute(
                'INSERT INTO queue_handoffs(namespace,identity,owner_key,epoch,intent,fingerprint,admission) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (
                    self.ticket.namespace,
                    identity,
                    owner_key(intent['uid']),
                    self.ticket.value,
                    jsonb(intent),
                    digest,
                    jsonb(admission),
                ),
            )
            mutate(conn, intent['payload'], admission)
            saved.append(admission)

        self.fence.admit_from_authority(self.client, intent['uid'], intent['conversation_ids'], persist)
        return saved[-1]

    def complete(self, conn, identity, envelope):
        """Seal in the SAME transaction as the queue's terminal result commit."""
        row = self._required_row(conn, identity)
        self._guard(conn, row)
        # Re-read after namespace serialization; a concurrent sealer may have won.
        row = self._required_row(conn, identity)
        envelope = bounded(envelope)
        digest = fingerprint(envelope)
        if row['completion_hash'] is not None:
            if row['completion_hash'] != digest:
                raise AuthorityRefused('completion is immutable')
            return digest
        conn.execute(
            "UPDATE queue_handoffs SET phase='completed',completion=%s,completion_hash=%s "
            'WHERE namespace=%s AND identity=%s',
            (jsonb(envelope), digest, self.ticket.namespace, identity),
        )
        return digest

    def export(self, identity):
        """Publish an immutable envelope, without copying a live queue into FS."""
        with self.pool.connection() as conn, conn.transaction():
            row = self._required_row(conn, identity)
            self._guard(conn, row)
            if row['completion_hash'] is None:
                raise AuthorityRefused('completion not committed')
            packet = bounded(
                {
                    key: row[key]
                    for key in (
                        'namespace',
                        'identity',
                        'owner_key',
                        'epoch',
                        'fingerprint',
                        'intent',
                        'admission',
                        'completion',
                        'completion_hash',
                    )
                }
            )
            # jsonb carries tagged datetimes; decode for the FS client.
            packet = codec.loads(codec.canonical(packet))
        from google.cloud import firestore

        @firestore.transactional
        def publish(transaction):
            self.authority.check(transaction, phases=('PG_OPEN',))
            ref = self.ref('completion', identity)
            previous = ref.get(transaction=transaction).to_dict()
            if previous:
                if fingerprint(previous) != fingerprint(packet):
                    raise AuthorityRefused('FS completion is immutable')
            else:
                transaction.create(ref, packet)

        publish(self.client.transaction())
        return packet

    def project(self, identity, operation):
        """Run customer projection and its durable receipt in ONE FS transaction.

        `operation(transaction, completion)` must use the existing projection
        transaction body and perform no external effects. Replays return the
        receipt, even if the caller lost the original Commit response. The caller
        must resolve group/sibling completion before choosing this identity.
        """
        from google.cloud import firestore
        from database.batch_pipeline_privacy import assert_batch_write_allowed
        from database.batch_privacy_attempt import TOKEN_FIELD

        with self.pool.connection() as conn, conn.transaction():
            expected = self._required_row(conn, identity)
            self._guard(conn, expected)
            if expected['completion_hash'] is None:
                raise AuthorityRefused('completion not committed')

        @firestore.transactional
        def commit(transaction):
            self.authority.check(transaction, phases=('PG_OPEN',))
            packet = self.ref('completion', identity).get(transaction=transaction).to_dict() or {}
            if (
                packet.get('epoch') != self.ticket.value
                or packet.get('namespace') != self.ticket.namespace
                or packet.get('identity') != identity
                or packet.get('completion_hash') != fingerprint(packet.get('completion'))
            ):
                raise AuthorityRefused('missing or corrupt completion')
            token = (
                self.client.collection('batch_pipeline_privacy')
                .document(packet['owner_key'])
                .get(transaction=transaction)
            )
            intent, admission = packet['intent'], packet['admission']
            self._verify_receipt({**packet, 'admission_id': admission['admission_id']}, expected)
            if fingerprint(intent) != packet['fingerprint']:
                raise AuthorityRefused('completion intent fingerprint changed')
            assert_batch_write_allowed(
                self.client, transaction, intent['uid'], conversation_ids=intent['conversation_ids'], snapshots={}
            )
            if (token.to_dict() or {}).get(TOKEN_FIELD) != admission['privacy_token']:
                raise AuthorityRefused('projection admission token changed')
            ref = self.ref('receipt', identity)
            previous = ref.get(transaction=transaction).to_dict()
            if previous:
                self._verify_receipt(previous, packet)
                return previous['result']
            result = bounded(operation(transaction, packet['completion']))
            receipt = dict(
                namespace=self.ticket.namespace,
                identity=identity,
                epoch=self.ticket.value,
                completion_hash=packet['completion_hash'],
                fingerprint=packet['fingerprint'],
                admission_id=admission['admission_id'],
                result=result,
            )
            # No expiry while PG acknowledgement is unknown. Customer projection
            # and this record are atomically durable; no post-Commit observer.
            transaction.create(ref, receipt)
            return result

        return commit(self.client.transaction())

    @staticmethod
    def _verify_receipt(receipt, packet):
        expected = {key: packet[key] for key in ('namespace', 'identity', 'epoch', 'completion_hash', 'fingerprint')}
        expected['admission_id'] = packet['admission']['admission_id']
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise AuthorityRefused('projection receipt binding mismatch')

    def ack(self, identity):
        # Read FS first, never under a PG pool slot/transaction/guard.
        receipt = self.ref('receipt', identity).get().to_dict()
        if not receipt:
            raise AuthorityRefused('durable projection receipt required')
        with self.pool.connection() as conn, conn.transaction():
            row = self._required_row(conn, identity)
            self._guard(conn, row)
            row = self._required_row(conn, identity)
            self._verify_receipt(receipt, row)
            digest = fingerprint(receipt)
            if row['phase'] == 'acked':
                if row['projection_receipt'] != digest:
                    raise AuthorityRefused('acknowledged receipt changed')
                return False
            if row['phase'] != 'completed':
                raise AuthorityRefused('uncompleted handoff')
            conn.execute(
                "UPDATE queue_handoffs SET phase='acked',projection_receipt=%s " 'WHERE namespace=%s AND identity=%s',
                (digest, self.ticket.namespace, identity),
            )
            return True
