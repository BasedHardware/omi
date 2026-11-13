"""Dark recording-scoped view for the existing customer projection protocol.

These documents are projection custody, never runnable FS queue rows. Missing
published views refuse rather than reconstruct data after purge. Outstanding
views have no invented TTL; production retained-copy purge remains a gate.
"""

from copy import deepcopy
from typing import cast

from google.cloud import firestore

from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_session import ProjectionSession
from database.batch_pipeline_projection_protocol import ProjectionPredecessorPending
from database.batch_pipeline_store import FirestoreStore, FirestoreTransaction
from database.batch_privacy_attempt import TOKEN_FIELD, token_version
from database.jobstore import codec
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.handoff import bounded
from database.jobstore.provider_handoff import PROTOCOL, validate_provider_payload, seal_recording
from database.privacy_fence.protocol import row_dict
from utils.batch_pipeline.contracts import WorkResult


class ProviderProjection(ProjectionStore):
    def __init__(self, handoff, identity):
        self.handoff, self.identity = handoff, identity
        with handoff.pool.connection() as conn, conn.transaction():
            row = handoff._required_row(conn, identity)
            handoff._guard(conn, row)
            if row['completion_hash'] is None or row['completion_hash'] != fingerprint(row['completion']):
                raise AuthorityRefused('sealed provider completion required')
            self.packet = codec.loads(
                codec.canonical(
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
            )
        self.binding = validate_provider_payload(self.packet['intent']['payload'])
        completion = self.packet['completion']
        units = completion.get('units', [])
        if (
            completion.get('protocol') != PROTOCOL
            or completion.get('recording_id') != identity
            or self.binding.job_id != identity
            or [unit['unit_id'] for unit in units] != list(self.binding.segment_ids)
        ):
            raise AuthorityRefused('provider projection census mismatch')
        self.expected = {}
        previous = None
        for unit in units:
            sid, source = unit['unit_id'], unit['source']
            if (
                unit['state'] != 'result_ready'
                or fingerprint(source) != fingerprint(self.packet['intent']['payload']['jobs'][sid])
                or WorkResult(**unit['result']).segment_id != sid
            ):
                raise AuthorityRefused('provider recovery cohort requires its projection adapter')
            self.expected['jobs', sid] = {
                **source,
                'state': 'committed',
                'merge_pending': False,
                'result': unit['result'],
            }
            self.expected['results', sid] = dict(
                segment_id=sid,
                owner_key=self.packet['owner_key'],
                capture_at=source['capture_at'],
                protocol_version=1,
                result=unit['result'],
                previous_segment_id=previous,
                committed_at=unit['settled_at'],
            )
            previous = sid
        self.owner = {
            'owner_key': self.packet['owner_key'],
            'recording_id': identity,
            'completion_hash': self.packet['completion_hash'],
            'retained_copy_manifest': self.custody_manifest(),
        }
        super().__init__(_ViewStore(self))

    def custody_manifest(self):
        """Exact new retained-copy census; this is not a purge certificate."""
        return (
            [
                {
                    'table': table,
                    'unit_id': sid,
                    'path': self.ref(table, sid).path,
                    'original_custody_deadline': self.packet['intent']['payload']['jobs'][sid]['typed_provider'][
                        'custody_deadline'
                    ],
                }
                for sid in self.binding.segment_ids
                for table in ('jobs', 'results')
            ]
            + [
                {'kind': kind, 'path': self.handoff.ref(kind, self.identity).path}
                for kind in ('intent', 'completion', 'receipt')
            ]
            + [
                {'kind': 'projection_cursor', 'path': self.ref('owners', self.packet['owner_key']).path},
                {'kind': 'original_intake', 'path': self.ref('intakes', self.identity).path},
            ]
        )

    def ref(self, table, key):
        if table == 'intakes' and key == self.identity:
            return self.handoff.client.collection(self.handoff.ticket.namespace + '_intakes').document(key)
        if (table, key) in self.expected or table == 'owners' and key == self.packet['owner_key']:
            return self.handoff.ref('provider_projection_' + table, self.identity + '/' + key)
        raise AuthorityRefused('cross-recording or unknown projection view')

    def _pg(self):
        # Finish this transaction BEFORE any FS RPC, including SDK retry bodies.
        with self.handoff.pool.connection() as conn, conn.transaction():
            row = self.handoff._required_row(conn, self.identity)
            self.handoff._guard(conn, row)
            if any(row[key] != self.packet[key] for key in ('fingerprint', 'completion_hash', 'admission')):
                raise AuthorityRefused('provider projection admission changed')
            return row['phase']

    def _e1_admission(self):
        # G2 4.9: benign authority writes (including our own assignment) rotate
        # F. Obtain a fresh E1 snapshot through A1/walk/A2, without changing the
        # original paid admission or adopting its result after a restore.
        def authorize(conn, admission):
            row = self.handoff._required_row(conn, self.identity)
            self.handoff._guard(conn, row)
            original = self.packet['admission']
            if any(
                admission[key] != original[key]
                for key in ('privacy_generation', 'privacy_change_seq', 'privacy_targets')
            ):
                raise AuthorityRefused('provider E1 re-admission cannot adopt a restored result')

        return self.handoff.fence.admit_from_authority(
            self.handoff.client, self.binding.owner_id, self.packet['intent']['conversation_ids'], authorize
        )

    def _privacy(self, transaction):
        admission = self._e1_admission()
        self.handoff.authority.check(transaction, phases=('PG_OPEN',))
        token = (
            self.handoff.client.collection('batch_pipeline_privacy')
            .document(self.packet['owner_key'])
            .get(transaction=transaction)
        )
        if token_version(token) is None or (token.to_dict() or {}).get(TOKEN_FIELD) != admission['privacy_token']:
            raise AuthorityRefused('provider projection admission token changed')
        assert_batch_write_allowed(
            self.handoff.client,
            transaction,
            self.binding.owner_id,
            conversation_ids=self.packet['intent']['conversation_ids'],
            expected_generation=self.binding.privacy_generation,
            snapshots={},
        )

    @staticmethod
    def _matches(actual, expected):
        return all(fingerprint(actual.get(key)) == fingerprint(value) for key, value in expected.items())

    def guard(self, transaction):
        self._pg()
        self._privacy(transaction)
        root = self.handoff.ref('completion', self.identity).get(transaction=transaction).to_dict() or {}
        if fingerprint(root) != fingerprint(self.packet):
            raise AuthorityRefused('missing or changed provider completion view')
        snapshots = {}
        for address, expected in self.expected.items():
            value = self.ref(*address).get(transaction=transaction).to_dict() or {}
            if not self._matches(value, expected):
                raise AuthorityRefused('missing or changed provider sibling view')
            snapshots[address] = value
        owner = self.ref('owners', self.packet['owner_key']).get(transaction=transaction).to_dict() or {}
        if not self._matches(owner, self.owner):
            raise AuthorityRefused('provider projection cursor binding changed')
        intake = self.ref('intakes', self.identity).get(transaction=transaction).to_dict() or {}
        original = self.packet['intent']['payload']['intakes'].get(self.identity, {})
        if not self._matches(intake, original):
            raise AuthorityRefused('original provider intake receipt changed')
        return snapshots

    def prepare(self):
        phase = self._pg()
        bounded(self.packet)

        @firestore.transactional
        def publish(transaction):
            self._privacy(transaction)
            root_ref = self.handoff.ref('completion', self.identity)
            root = root_ref.get(transaction=transaction).to_dict()
            values = {address: self.ref(*address).get(transaction=transaction).to_dict() for address in self.expected}
            owner_ref = self.ref('owners', self.packet['owner_key'])
            owner = owner_ref.get(transaction=transaction).to_dict()
            if root is not None:
                # Atomic publication cannot legitimately leave missing children.
                self.guard(transaction)
                return False
            if phase != 'completed' or owner is not None or any(value is not None for value in values.values()):
                raise AuthorityRefused('partial or retired provider projection view')
            original = self.packet['intent']['payload']['intakes'].get(self.identity, {})
            intake = self.ref('intakes', self.identity).get(transaction=transaction).to_dict() or {}
            if not self._matches(intake, original):
                raise AuthorityRefused('original provider intake receipt changed')
            transaction.create(root_ref, self.packet)
            for address, expected in self.expected.items():
                transaction.create(
                    self.ref(*address),
                    {**expected, **({'projection_state': 'pending'} if address[0] == 'results' else {})},
                )
            transaction.create(owner_ref, {**self.owner, 'projection_watermark': None})
            return True

        return publish(self.client.transaction())

    def _mirror(self, binding, extra=()):
        # Private projection custody is not the legacy runnable queue shadow.
        pass

    def session(self, segment_id, binding, now, **part):
        if binding != self.binding:
            raise AuthorityRefused('cross-recording projection session')
        return _Session(self, segment_id, binding, now, **part)

    def read(self, segment_id):
        self.policy(segment_id)

        @firestore.transactional
        def read(transaction):
            snapshots = self.guard(transaction)
            return deepcopy(snapshots['jobs', segment_id]), deepcopy(snapshots['results', segment_id]), self.binding

        return read(self.client.transaction())

    def run(self, operation, *, policy=None):
        body = getattr(operation, 'to_wrap', None)
        if body is None:
            raise AuthorityRefused('transactional projection operation required')

        @firestore.transactional
        def guarded(transaction):
            self.guard(transaction)
            return body(transaction)

        return super().run(guarded, policy=policy)

    def _prepare_completion_receipt(self, transaction, binding):
        if binding != self.binding:
            raise AuthorityRefused('provider completion binding mismatch')
        old = self.handoff.ref('receipt', self.identity).get(transaction=transaction).to_dict()
        if old:
            if old.get('projection_protocol') != PROTOCOL or old.get('owner_key') != self.packet['owner_key']:
                raise AuthorityRefused('concrete provider customer receipt required')
            self.handoff._verify_receipt(old, self.packet)
        return old

    def _write_completion_receipt(self, transaction, binding, result, context):
        previous = context
        if previous:
            if previous.get('result') != result:
                raise AuthorityRefused('immutable provider customer completion changed')
            return
        receipt = {
            key: self.packet[key]
            for key in ('namespace', 'identity', 'owner_key', 'epoch', 'fingerprint', 'completion_hash')
        }
        receipt.update(
            admission_id=self.packet['admission']['admission_id'], projection_protocol=PROTOCOL, result=result
        )
        transaction.create(self.handoff.ref('receipt', self.identity), bounded(receipt))

    def retain_completed(self, uid, segment_id, now):
        # This new custody family must not inherit the legacy live queue TTL.
        # Unacknowledged PG custody survives unknown COMMIT. Original object
        # lifetimes remain unchanged; a production cleanup/purge manifest and
        # per-record lifetime adapter remain serving gates.
        if uid != self.binding.owner_id or segment_id not in self.binding.segment_ids:
            raise AuthorityRefused('provider retention binding mismatch')

        @firestore.transactional
        def check(transaction):
            self.guard(transaction)
            receipt = self.handoff.ref('receipt', self.identity).get(transaction=transaction).to_dict()
            if not receipt:
                return False
            self.handoff._verify_receipt(receipt, self.packet)
            return True

        return check(self.client.transaction())

    def ack(self, *, now):
        receipt = self.handoff.ref('receipt', self.identity).get().to_dict()
        if (
            not receipt
            or receipt.get('projection_protocol') != PROTOCOL
            or receipt.get('owner_key') != self.packet['owner_key']
        ):
            raise AuthorityRefused('durable provider customer receipt required')
        with self.handoff.pool.connection() as conn, conn.transaction():
            changed = self.handoff.ack_in_transaction(conn, self.identity, receipt)
            conn.execute("SELECT set_config('omi.queue_owner_key',%s,true)", (self.packet['owner_key'],))
            recording = row_dict(
                conn,
                'SELECT * FROM recordings WHERE namespace=%s AND recording_id=%s FOR UPDATE',
                (self.packet['namespace'], self.identity),
            )
            if (
                not recording
                or recording['owner_key'] != self.packet['owner_key']
                or recording['projection_state'] == 'revoked'
                or recording['units_final'] != len(self.binding.segment_ids)
                or recording['units_total'] != len(self.binding.segment_ids)
                or recording['projection_task_id'] is None
            ):
                raise AuthorityRefused('provider ack recording census mismatch')
            # Revalidate the current full terminal census against its original
            # immutable seal in the same acknowledgement transaction.
            seal_recording(conn, self.handoff, recording)
            custody = conn.execute(
                'SELECT identity,phase,owner_key,admission_id FROM queue_custody WHERE namespace=%s AND identity=ANY(%s) FOR UPDATE',
                (self.packet['namespace'], list(self.binding.segment_ids)),
            ).fetchall()
            if len(custody) != len(self.binding.segment_ids) or any(
                phase not in {'completed', 'acked'}
                or owner != self.packet['owner_key']
                or str(admission) != self.packet['admission']['admission_id']
                for _, phase, owner, admission in custody
            ):
                raise AuthorityRefused('provider ack original custody mismatch')
            task = row_dict(
                conn,
                'SELECT * FROM outbox WHERE namespace=%s AND id=%s FOR UPDATE',
                (self.packet['namespace'], recording['projection_task_id']),
            )
            if (
                not task
                or task['kind'] != 'project_conversation'
                or task['dedupe_key'] != self.identity
                or task['owner_id'] != self.packet['owner_key']
            ):
                raise AuthorityRefused('provider ack projection task mismatch')
            conn.execute(
                "UPDATE recordings SET projection_state='projected' WHERE namespace=%s AND recording_id=%s",
                (self.packet['namespace'], self.identity),
            )
            conn.execute(
                "UPDATE queue_custody SET phase='acked',projection_receipt=%s WHERE namespace=%s AND identity=ANY(%s)",
                (fingerprint(receipt), self.packet['namespace'], list(self.binding.segment_ids)),
            )
            conn.execute(
                "UPDATE outbox SET done_at=coalesce(done_at,%s),done_reason='projected',lease_token=NULL,lease_until=0,wake_token=NULL,wake_pending=false WHERE namespace=%s AND id=%s",
                (now, self.packet['namespace'], recording['projection_task_id']),
            )
            return changed


class _Session(ProjectionSession):
    def prepare(self, transaction, **options):
        projection = cast(ProviderProjection, self.store)
        snapshots = projection.guard(transaction)
        entry = snapshots['results', self.segment_id]
        owner = self.owner_ref.get(transaction=transaction).to_dict() or {}
        receipt = (
            (entry.get('projection_parts') or {}).get(str(self.part_index))
            if self.part_index is not None
            else entry.get('projection')
        )
        if not receipt and entry.get('previous_segment_id') != owner.get('projection_watermark'):
            # No legacy erased-chain lookup can authorize this private cursor.
            raise ProjectionPredecessorPending('earlier recording projection must persist first')
        return super().prepare(transaction, **options)


class _ViewTransaction(FirestoreTransaction):
    def __init__(self, projection, transaction):
        super().__init__(projection.client, projection.handoff.ticket.namespace, transaction)
        self.projection = projection

    def _ref(self, table, key):
        if table in {'content', 'conversations'}:
            return super()._ref(table, key)
        return self.projection.ref(table, key)


class _ViewStore(FirestoreStore):
    def __init__(self, projection):
        self.projection = projection
        super().__init__(projection.handoff.ticket.namespace, firestore_client=projection.handoff.client)

    def run(self, body):
        @firestore.transactional
        def commit(transaction):
            self.projection.guard(transaction)
            view = _ViewTransaction(self.projection, transaction)
            result = body(view)
            view.flush()
            return result

        return commit(self.client.transaction())
