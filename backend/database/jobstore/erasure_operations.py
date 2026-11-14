"""Durable PG progress barriers for the real legal-hold destructive gate.

No callback crosses this boundary. A committed row records only a completed
remote-copy phase; it cannot release original custody or certify cold sinks.
Cancellation locks the same row as execution, fencing a paused old executor.
Missing rows, lock timeouts and transport failures never prove rollback.
"""

from uuid import uuid4

from psycopg import Error as PostgresError  # pyright: ignore[reportMissingImports]

from database.jobstore.authority import AuthorityRefused
from database.jobstore.postgres_store import jsonb
from database.privacy_fence.protocol import lock, owner_key, row_dict

PREFIX = 'jobstore-erasure-v1:'


class ErasureOperations:
    def __init__(self, retained):
        self.retained = retained
        self.handoff = retained.handoff

    def prepare(self, uid, identity, authority, purpose, payload, *, conversation=None):
        if authority.uid != uid or authority.client is not self.handoff.client:
            raise AuthorityRefused('original erasure requires the real customer unit')
        operation = uuid4().hex
        with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
            privacy = self.retained._terminal(conn, owner_key(uid), conversation)
            generation = privacy['purge_generation'] if conversation is None else None
            if conversation is None and generation is None:
                raise AuthorityRefused('original account PG purge generation required')
            census = row_dict(
                conn,
                'SELECT * FROM queue_retained_copy_custody WHERE namespace=%s AND recording_id=%s',
                (self.handoff.ticket.namespace, identity),
            )
            if not census or census['owner_key'] != owner_key(uid) or census['phase'] != 'private_erased':
                raise AuthorityRefused('original erase requires durable private retirement')
            source = self.handoff._required_row(conn, identity)
            if source['owner_key'] != owner_key(uid):
                raise AuthorityRefused('original source ownership changed')
            if purpose in {'published_object', 'published_reference'}:
                from database.jobstore.published_copies import payload as upload_payload

                upload = row_dict(
                    conn,
                    'SELECT * FROM queue_provider_uploads WHERE namespace=%s AND unit_id=%s',
                    (self.handoff.ticket.namespace, payload.get('unit_id')),
                )
                if (
                    not upload
                    or upload['recording_id'] != identity
                    or upload['owner_key'] != owner_key(uid)
                    or upload['phase'] != 'published'
                    or str(upload['admission_id']) != source['admission']['admission_id']
                    or upload_payload(upload) != payload
                ):
                    raise AuthorityRefused('published object outside original upload custody')
                if (
                    purpose == 'published_reference'
                    and not conn.execute(
                        "SELECT 1 FROM queue_original_erasure_operations WHERE namespace=%s AND recording_id=%s AND purpose='published_object' AND state='committed' AND payload=%s LIMIT 1",
                        (self.handoff.ticket.namespace, identity, jsonb(payload)),
                    ).fetchone()
                ):
                    raise AuthorityRefused('published original object proof required before reference erasure')
            elif source['completion_hash'] != payload.get('completion_hash'):
                raise AuthorityRefused('original completion binding changed')
            uris = sorted(
                {
                    uri
                    for unit in (source['completion'] or {}).get('units', [])
                    for uri in (unit['source']['audio_uri'], unit['result']['result_uri'])
                }
            )
            if purpose in {'published_object', 'published_reference'}:
                pass
            elif purpose == 'object':
                if set(payload) != {'uri', 'completion_hash'} or payload['uri'] not in uris:
                    raise AuthorityRefused('object outside original recording census')
            elif purpose == 'metadata':
                if (
                    set(payload) != {'paths', 'uris', 'completion_hash'}
                    or payload['paths'] != census['manifest']['original_paths'][:3]
                    or payload['uris'] != uris
                ):
                    raise AuthorityRefused('metadata outside original recording census')
                for uri in uris:
                    if not conn.execute(
                        "SELECT 1 FROM queue_original_erasure_operations WHERE namespace=%s AND recording_id=%s "
                        "AND purpose='object' AND state='committed' AND payload=%s LIMIT 1",
                        (
                            self.handoff.ticket.namespace,
                            identity,
                            jsonb(dict(uri=uri, completion_hash=source['completion_hash'])),
                        ),
                    ).fetchone():
                        raise AuthorityRefused('original metadata still has unresolved object custody')
            else:
                raise AuthorityRefused('unknown original copy family')
            conn.execute(
                'INSERT INTO queue_original_erasure_operations '
                '(namespace,operation_id,recording_id,owner_key,unit_token,purpose,payload,purge_generation) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (
                    self.handoff.ticket.namespace,
                    operation,
                    identity,
                    owner_key(uid),
                    authority.token,
                    purpose,
                    jsonb(payload),
                    generation,
                ),
            )
        return PREFIX + self.handoff.ticket.namespace + ':' + operation

    def _row(self, conn, uid, target):
        prefix = PREFIX + self.handoff.ticket.namespace + ':'
        if not target.startswith(prefix) or len(target.removeprefix(prefix)) != 32:
            raise ConnectionError('unknown original erasure target; outcome unresolved')
        row = row_dict(
            conn,
            'SELECT * FROM queue_original_erasure_operations WHERE namespace=%s AND operation_id=%s FOR UPDATE',
            (self.handoff.ticket.namespace, target.removeprefix(prefix)),
        )
        if not row or row['owner_key'] != owner_key(uid):
            raise ConnectionError('missing or foreign operation is not rollback proof')
        return row

    def finish(self, uid, target, authority, *, conversation=None):
        """Called only after the exact remote phase succeeds, under remote().

        DB errors include an uncertain COMMIT reply. Normalize all of them to
        an unknown transport outcome for UnitAuthority; its generic HTTP
        classifier cannot interpret psycopg errors. Never return False.
        """
        try:
            with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
                privacy = self.retained._terminal(conn, owner_key(uid), conversation)
                row = self._row(conn, uid, target)
                if row['purge_generation'] is not None and (
                    privacy['state'] != 'purging' or privacy['purge_generation'] != row['purge_generation']
                ):
                    raise AuthorityRefused('original PG purge generation changed')
                if row['unit_token'] != authority.token or authority.uid != uid:
                    raise AuthorityRefused('original destructive-unit token changed')
                if row['state'] == 'cancelled':
                    raise AuthorityRefused('original erasure operation cancelled')
                if row['state'] == 'prepared':
                    conn.execute(
                        "UPDATE queue_original_erasure_operations SET state='committed' WHERE namespace=%s AND operation_id=%s",
                        (row['namespace'], row['operation_id']),
                    )
        except PostgresError as error:
            raise ConnectionError('original erasure PG outcome unresolved') from error

    def resolve(self, uid, target):
        """Definitive COMMIT or durable cancellation, never absence-as-rollback.

        L_x precedes the operation row lock on both paths. A running executor's
        transaction must finish before recovery can cancel; a paused executor
        sees cancelled before doing anything. Recovery does not require the old
        epoch to remain current merely to cancel an unexecuted progress write.
        """
        try:
            with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
                lock(conn, owner_key(uid), exclusive=True)
                row = self._row(conn, uid, target)
                if row['state'] == 'prepared':
                    conn.execute(
                        "UPDATE queue_original_erasure_operations SET state='cancelled' WHERE namespace=%s AND operation_id=%s",
                        (row['namespace'], row['operation_id']),
                    )
            return True
        except PostgresError as error:
            raise ConnectionError('original erasure recovery PG outcome unresolved') from error
