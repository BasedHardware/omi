"""Real destructive PG artifact-copy units with durable cancellation barriers.

Original FS intake/staging and PG reference custody survive. DELETEs, their
journal entries and the operation outcome share COMMIT. No absence-as-rollback,
lease expiry, callback or progress-only receipt certifies that transaction.
"""

from uuid import uuid4

from psycopg import Error as PostgresError  # pyright: ignore[reportMissingImports]

from database.jobstore import codec
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.postgres_store import jsonb
from database.privacy_fence.protocol import lock, owner_key, row_dict

PREFIX = 'jobstore-staging-v1:'


def artifact_fingerprint(value):
    return fingerprint({key: item for key, item in value.items() if key != 'erasure_requested'})


class StagingOperations:
    def __init__(self, retained):
        self.retained, self.handoff = retained, retained.handoff

    def prepare(self, uid, identity, authority, manifest, *, conversation=None):
        operation = uuid4().hex
        with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
            privacy = self.retained._terminal(conn, owner_key(uid), conversation)
            source = self.handoff._required_row(conn, identity)
            if authority.uid != uid or authority.client is not self.handoff.client:
                raise AuthorityRefused('staging operation requires original customer authority')
            digest = fingerprint(dict(intent=source['intent'], admission=source['admission']))
            if manifest['source_fingerprint'] != digest or manifest['owner_key'] != owner_key(uid):
                raise AuthorityRefused('staging source census changed')
            if not conn.execute(
                "SELECT 1 FROM queue_original_erasure_operations WHERE namespace=%s AND recording_id=%s "
                "AND purpose='metadata' AND state='committed' AND payload->>'completion_hash'=%s LIMIT 1",
                (self.handoff.ticket.namespace, identity, source['completion_hash']),
            ).fetchone():
                raise AuthorityRefused('original metadata/object phase still unresolved')
            generation = privacy['purge_generation'] if conversation is None else None
            if conversation is None and generation is None:
                raise AuthorityRefused('staging account purge generation required')
            old = conn.execute(
                'SELECT manifest FROM queue_staging_copy_custody WHERE namespace=%s AND recording_id=%s',
                (self.handoff.ticket.namespace, identity),
            ).fetchone()
            if old and fingerprint(old[0]) != fingerprint(manifest):
                raise AuthorityRefused('immutable original staging census changed')
            if not old:
                conn.execute(
                    'INSERT INTO queue_staging_copy_custody(namespace,recording_id,owner_key,manifest) VALUES (%s,%s,%s,%s)',
                    (self.handoff.ticket.namespace, identity, owner_key(uid), jsonb(manifest)),
                )
                for artifact in manifest['artifacts']:
                    conn.execute(
                        'INSERT INTO queue_staging_copy_keys(namespace,key,recording_id,owner_key,cold_path) '
                        'VALUES (%s,%s,%s,%s,%s)',
                        (
                            self.handoff.ticket.namespace,
                            artifact['key'],
                            identity,
                            owner_key(uid),
                            artifact['cold_path'],
                        ),
                    )
            conn.execute(
                'INSERT INTO queue_staging_erasure_operations '
                '(namespace,operation_id,recording_id,owner_key,unit_token,census_hash,purge_generation) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (
                    self.handoff.ticket.namespace,
                    operation,
                    identity,
                    owner_key(uid),
                    authority.token,
                    fingerprint(manifest),
                    generation,
                ),
            )
        return PREFIX + self.handoff.ticket.namespace + ':' + operation

    def _row(self, conn, uid, target):
        prefix = PREFIX + self.handoff.ticket.namespace + ':'
        if not target.startswith(prefix) or len(target.removeprefix(prefix)) != 32:
            raise ConnectionError('unknown staging operation; outcome unresolved')
        row = row_dict(
            conn,
            'SELECT * FROM queue_staging_erasure_operations WHERE namespace=%s AND operation_id=%s FOR UPDATE',
            (self.handoff.ticket.namespace, target.removeprefix(prefix)),
        )
        if not row or row['owner_key'] != owner_key(uid):
            raise ConnectionError('missing or foreign staging operation is not rollback proof')
        return row

    def manifest(self, uid, target):
        with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
            lock(conn, owner_key(uid), exclusive=True)
            row = self._row(conn, uid, target)
            value = conn.execute(
                'SELECT manifest FROM queue_staging_copy_custody WHERE namespace=%s AND recording_id=%s',
                (row['namespace'], row['recording_id']),
            ).fetchone()[0]
            if fingerprint(value) != row['census_hash']:
                raise AuthorityRefused('staging manifest binding changed')
            return value

    def execute(self, uid, target, authority, *, conversation=None):
        """Pure SQL; caller pins the actual unit gate and verifies FS custody first."""
        try:
            with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
                privacy = self.retained._terminal(conn, owner_key(uid), conversation)
                row = self._row(conn, uid, target)
                if authority.uid != uid or row['unit_token'] != authority.token:
                    raise AuthorityRefused('staging destructive-unit token changed')
                if row['state'] == 'cancelled':
                    raise AuthorityRefused('staging operation cancelled')
                if row['purge_generation'] is not None and privacy['purge_generation'] != row['purge_generation']:
                    raise AuthorityRefused('staging PG purge generation changed')
                if row['state'] == 'committed':
                    return
                manifest = conn.execute(
                    'SELECT manifest FROM queue_staging_copy_custody WHERE namespace=%s AND recording_id=%s',
                    (row['namespace'], row['recording_id']),
                ).fetchone()[0]
                if fingerprint(manifest) != row['census_hash']:
                    raise AuthorityRefused('staging operation census changed')
                if manifest['epoch'] != self.handoff.ticket.value:
                    raise AuthorityRefused('staging operation belongs to an older queue epoch')
                conn.execute("SELECT set_config('omi.queue_epoch',%s,true)", (str(self.handoff.ticket.value),))
                conn.execute("SELECT set_config('omi.queue_owner_key',%s,true)", (owner_key(uid),))
                conn.execute("SELECT set_config('omi.staging_erasure_operation',%s,true)", (row['operation_id'],))
                for artifact in manifest['artifacts']:
                    copy = conn.execute(
                        "SELECT doc FROM docs WHERE namespace=%s AND tbl='artifacts' AND key=%s FOR UPDATE",
                        (row['namespace'], artifact['key']),
                    ).fetchone()
                    if copy and artifact_fingerprint(codec.loads(codec.dumps(copy[0]))) != artifact['fingerprint']:
                        raise AuthorityRefused('staging PG copy differs from original retained FS source')
                    conn.execute(
                        "DELETE FROM docs WHERE namespace=%s AND tbl='artifacts' AND key=%s",
                        (row['namespace'], artifact['key']),
                    )
                conn.execute(
                    "UPDATE queue_staging_erasure_operations SET state='committed' WHERE namespace=%s AND operation_id=%s",
                    (row['namespace'], row['operation_id']),
                )
        except PostgresError as error:
            raise ConnectionError('staging destructive PG outcome unresolved') from error

    def resolve(self, uid, target):
        try:
            with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
                lock(conn, owner_key(uid), exclusive=True)
                row = self._row(conn, uid, target)
                if row['state'] == 'prepared':
                    conn.execute(
                        "UPDATE queue_staging_erasure_operations SET state='cancelled' WHERE namespace=%s AND operation_id=%s",
                        (row['namespace'], row['operation_id']),
                    )
            return True
        except PostgresError as error:
            raise ConnectionError('staging recovery PG outcome unresolved') from error
