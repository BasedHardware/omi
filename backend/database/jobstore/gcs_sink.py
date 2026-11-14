"""Real terminal-session drain with a durable barrier against late COMPLETE.

This adapter is explicit/dark. Local transport tests do not qualify remote C4.
"""

from dataclasses import dataclass

from google.cloud import firestore
from psycopg import Error as PostgresError  # pyright: ignore[reportMissingImports]

from database import legal_holds
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.gcs_transport import GCSTransport
from database.privacy_fence import FenceRefused
from database.privacy_fence.protocol import lock, row_dict, owner_key

PREFIX = 'jobstore-gcs-v1:'


@dataclass(frozen=True)
class TerminalProof:
    sink_hash: str
    status: int
    generation: int | None


class GCSSink:
    def __init__(self, handoff, storage_client, *, timeout, authority=None, recovery_target=None):
        self.handoff, self.pool = handoff, handoff.pool
        self.transport = GCSTransport(storage_client, timeout=timeout)
        self.authority, self.recovery_target = authority, recovery_target

    def _gate(self, uid, target):
        authority = self.authority
        if (
            not isinstance(authority, legal_holds.UnitAuthority)
            or authority.uid != uid
            or authority.client is not self.handoff.client
        ):
            raise AuthorityRefused('actual legal-hold destructive-unit authority required for GCS drain')

        @firestore.transactional
        def check(transaction):
            authority.fence(transaction)
            self.handoff.authority.check(
                transaction, phases=('PG_OPEN', 'PG_CLOSING', 'BOTH_CLOSED', 'FS_OPEN', 'FS_CLOSING')
            )
            if self.recovery_target is not None:
                gate = (
                    self.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION)
                    .document(uid)
                    .get(transaction=transaction)
                    .to_dict()
                    or {}
                )
                if not gate.get('remote_inflight') or gate.get('remote_target') != target:
                    raise ConnectionError('GCS recovery target changed')

        check(self.handoff.client.transaction())

    def _row(self, conn, sink):
        if set(sink) != {'protocol', 'namespace', 'unit_id', 'attempt_token', 'bucket', 'key', 'size', 'session'} or (
            sink['protocol'] != 'typed-result-session-v1'
            or sink['namespace'] != self.handoff.ticket.namespace
            or type(sink['size']) is not int
            or not 0 < sink['size'] <= 8 * 1024 * 1024 + 34
        ):
            raise AuthorityRefused('unsupported GCS source cohort')
        row = row_dict(
            conn,
            'SELECT * FROM queue_provider_uploads WHERE namespace=%s AND unit_id=%s ' 'AND attempt_token=%s FOR UPDATE',
            (sink['namespace'], sink['unit_id'], sink['attempt_token']),
        )
        if not row or row['bucket'] != sink['bucket'] or row['object_key'] != sink['key']:
            raise ConnectionError('original GCS source custodian missing or changed')
        original = self.handoff._required_row(conn, row['recording_id'])
        uid = original['intent']['uid']
        if row['owner_key'] != owner_key(uid) or str(row['admission_id']) != original['admission']['admission_id']:
            raise AuthorityRefused('GCS original paid admission changed')
        return row, uid

    def __call__(self, sink):
        try:
            # Owner before row; no slot/guard crosses a storage request. An
            # open-owner lease janitor must exclude a concurrent valid COMPLETE
            # before deleting a finalized object, not merely cancel the session.
            with self.pool.connection(timeout=2) as conn, conn.transaction():
                before = conn.execute(
                    'SELECT owner_key FROM queue_provider_uploads WHERE namespace=%s AND unit_id=%s '
                    'AND attempt_token=%s',
                    (sink.get('namespace'), sink.get('unit_id'), sink.get('attempt_token')),
                ).fetchone()
                if not before:
                    raise ConnectionError('missing original GCS custodian is not terminal proof')
                lock(conn, before[0], exclusive=True)
                row, uid = self._row(conn, sink)
                effect = self.handoff.fence._effect(conn, row['owner_key'], row['effect_id'])
                if row['phase'] in {'published', 'fenced'} and effect is None:
                    return None
                if not effect or effect['sink'] != sink or row['phase'] not in {'registered', 'draining'}:
                    raise ConnectionError('GCS capability/original custody unresolved')
                target = PREFIX + row['namespace'] + ':' + str(row['effect_id'])
            self._gate(uid, target)
            with self.pool.connection(timeout=2) as conn, conn.transaction():
                lock(conn, row['owner_key'], exclusive=True)
                row, uid = self._row(conn, sink)
                effect = self.handoff.fence._effect(conn, row['owner_key'], row['effect_id'])
                if effect is None and row['phase'] in {'published', 'fenced'}:
                    return None
                if not effect or effect['sink'] != sink or row['phase'] not in {'registered', 'draining'}:
                    raise ConnectionError('original GCS effect/custody changed')
                try:
                    original = self.handoff._required_row(conn, row['recording_id'])
                    self.handoff.fence.check_work_write(conn, row['owner_key'], original['admission'])
                    allowed = True
                except FenceRefused:
                    allowed = False
                if (
                    row['phase'] != 'draining'
                    and allowed
                    and effect['lease_until'] > conn.execute('SELECT now()').fetchone()[0]
                ):
                    return None
                self._epoch(conn)
                conn.execute(
                    "UPDATE queue_provider_uploads SET phase='draining' WHERE namespace=%s AND unit_id=%s AND attempt_token=%s",
                    (row['namespace'], row['unit_id'], row['attempt_token']),
                )
            call = lambda: self.transport.fence(sink, uid=uid, known_generation=row['generation'])
            status, generation = (
                call() if self.recovery_target is not None else self.authority.remote(call, target=target)
            )
            return TerminalProof(fingerprint(sink), status, generation)
        except PostgresError as error:
            raise ConnectionError('GCS drain PG barrier outcome unresolved') from error

    def retire(self, conn, effect, proof):
        if not isinstance(proof, TerminalProof) or proof.sink_hash != fingerprint(effect['sink']):
            raise AuthorityRefused('actual original GCS terminal proof required')
        row, _ = self._row(conn, effect['sink'])
        if row['phase'] != 'draining' or str(row['effect_id']) != str(effect['effect_id']):
            raise AuthorityRefused('GCS drain barrier changed')
        if row['generation'] is not None and proof.generation != row['generation']:
            raise AuthorityRefused('GCS drain original generation changed')
        self._epoch(conn)
        conn.execute(
            "UPDATE queue_provider_uploads SET phase='fenced',generation=%s WHERE namespace=%s AND unit_id=%s AND attempt_token=%s",
            (proof.generation, row['namespace'], row['unit_id'], row['attempt_token']),
        )

    def finish(self, sink):
        try:
            return self._finish(sink)
        except PostgresError as error:
            raise ConnectionError('GCS final PG outcome unresolved') from error

    def _epoch(self, conn):
        epoch = conn.execute(
            'SELECT epoch FROM queue_authority WHERE namespace=%s', (self.handoff.ticket.namespace,)
        ).fetchone()
        if not epoch or epoch[0] != self.handoff.ticket.value:
            raise AuthorityRefused('GCS destructive namespace epoch changed')
        conn.execute("SELECT set_config('omi.queue_epoch',%s,true)", (str(epoch[0]),))

    def _finish(self, sink):
        proof = self(sink)
        if proof is None:
            return
        with self.pool.connection(timeout=2) as conn, conn.transaction():
            # _row requires row lock; acquire its immutable owner first.
            owner = conn.execute(
                'SELECT owner_key FROM queue_provider_uploads WHERE namespace=%s AND unit_id=%s AND attempt_token=%s',
                (sink['namespace'], sink['unit_id'], sink['attempt_token']),
            ).fetchone()
            if not owner:
                raise ConnectionError('original GCS custody missing')
            lock(conn, owner[0], exclusive=True)
            row, _ = self._row(conn, sink)
            effect = self.handoff.fence._effect(conn, row['owner_key'], row['effect_id'])
            if effect is None:
                return
            self._epoch(conn)
            self.retire(conn, effect, proof)
            self.handoff.fence._retire(conn, effect)

    def recover(self, uid, target):
        try:
            return self._recover(uid, target)
        except PostgresError as error:
            raise ConnectionError('GCS recovery PG outcome unresolved') from error

    def _recover(self, uid, target):
        prefix = PREFIX + self.handoff.ticket.namespace + ':'
        if not target.startswith(prefix):
            raise ConnectionError('foreign GCS recovery target')
        with self.pool.connection(timeout=2) as conn:
            source = row_dict(
                conn,
                'SELECT * FROM queue_provider_uploads WHERE namespace=%s AND effect_id::text=%s',
                (self.handoff.ticket.namespace, target.removeprefix(prefix)),
            )
            if not source or source['owner_key'] != owner_key(uid):
                raise ConnectionError('missing original GCS operation is not rollback proof')
            effect = row_dict(conn, 'SELECT * FROM privacy_effect_inflight WHERE effect_id=%s', (source['effect_id'],))
        if effect is None:
            if source['phase'] == 'fenced':
                return True
            raise ConnectionError('unresolved GCS recovery census')
        gate = (
            self.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION)
            .document(uid)
            .get()
            .to_dict()
            or {}
        )
        if not gate.get('remote_inflight') or gate.get('remote_target') != target:
            raise ConnectionError('original GCS gate target changed')
        authority = legal_holds.UnitAuthority(uid, gate['kind'], gate['token'], self.handoff.client, None)
        recovery = GCSSink(
            self.handoff,
            self.transport.client,
            timeout=self.transport.timeout,
            authority=authority,
            recovery_target=target,
        )
        recovery.finish(effect['sink'])
        return True
