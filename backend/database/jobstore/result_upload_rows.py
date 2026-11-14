"""Original typed result-object custody; capabilities live only in the registry."""

from uuid import uuid4

from database.jobstore.authority import AuthorityRefused, fingerprint, acquire
from database.privacy_fence.protocol import lock, row_dict


class ResultUploadRows:
    def __init__(self, ticket):
        self.ticket, self.units = ticket, ticket.units
        self.handoff, self.pool = ticket.handoff, ticket.units.pool

    def source(self, conn, *, pending=False):
        job = self.units._guarded_unit(conn, self.ticket.identity)
        if (
            not job
            or job['admission'] != self.ticket.admission
            or fingerprint(job['source']) != fingerprint(self.ticket.source)
        ):
            raise AuthorityRefused('result upload cannot adopt a restored source')
        if pending and (job['state'] != 'pending' or job['attempt_token'] != self.ticket.attempt):
            raise AuthorityRefused('original pending paid attempt required')
        if str(job['attempt_admission_id']) != self.ticket.admission['admission_id']:
            raise AuthorityRefused('original result attempt admission changed')
        return job

    def row(self, conn):
        return row_dict(
            conn,
            'SELECT * FROM queue_provider_uploads WHERE namespace=%s AND unit_id=%s ' 'AND attempt_token=%s FOR UPDATE',
            (self.units.namespace, self.ticket.identity, self.ticket.attempt),
        )

    def prepare(self, artifact_store, digest):
        with self.pool.connection(timeout=2) as conn, conn.transaction():
            job = self.source(conn, pending=True)
            existing = self.row(conn)
            if existing:
                if existing['content_hash'] != digest or existing['bucket'] != artifact_store.bucket_name:
                    raise AuthorityRefused('original result payload/bucket changed')
                if existing['phase'] != 'published':
                    raise ConnectionError('original upload outcome unresolved; no second session or PUT')
                return existing
            if conn.execute(
                'SELECT state FROM privacy_effect_inflight WHERE effect_id=%s', (self.ticket.effect,)
            ).fetchone() != ('started',):
                raise AuthorityRefused('actual paid provider START required before result upload')
            key = f'{artifact_store.owner_prefix(self.ticket.source["owner_id"])}results/{job["unit_id"]}/{uuid4().hex}.enc'
            conn.execute(
                'INSERT INTO queue_provider_uploads(namespace,unit_id,attempt_token,recording_id,owner_key,'
                'admission_id,object_key,bucket,content_hash,original_deadline) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (
                    self.units.namespace,
                    job['unit_id'],
                    self.ticket.attempt,
                    job['recording_id'],
                    job['owner_key'],
                    self.ticket.admission['admission_id'],
                    key,
                    artifact_store.bucket_name,
                    digest,
                    job['custody_deadline'],
                ),
            )
            reserved = self.row(conn)
            if reserved is None:
                raise ConnectionError('original upload reservation outcome unresolved')
            return reserved

    def register(self, session, row, size, *, lease_seconds):
        sink = dict(
            protocol='typed-result-session-v1',
            namespace=row['namespace'],
            unit_id=row['unit_id'],
            attempt_token=row['attempt_token'],
            bucket=row['bucket'],
            key=row['object_key'],
            size=size,
            session=session,
        )
        with self.pool.connection(timeout=2) as conn, conn.transaction():
            self.source(conn, pending=True)
            current = self.row(conn)
            if current is None or current != row or current['phase'] != 'prepared':
                raise AuthorityRefused('result registration reservation changed')
            effect = self.units.fence.register(
                conn,
                self.ticket.owner,
                self.ticket.identity,
                self.ticket.admission,
                'gcs_put',
                lease_seconds=lease_seconds,
                sink=sink,
            )
            conn.execute(
                "UPDATE queue_provider_uploads SET effect_id=%s,phase='registered' "
                'WHERE namespace=%s AND unit_id=%s AND attempt_token=%s',
                (effect, row['namespace'], row['unit_id'], row['attempt_token']),
            )
        return effect

    def start(self, effect):
        with self.pool.connection(timeout=2) as conn, conn.transaction():
            self.source(conn, pending=True)
            row = self.row(conn)
            if not row or row['phase'] != 'registered' or str(row['effect_id']) != effect:
                raise AuthorityRefused('original GCS dispatch already fenced')
            self.units.fence.start(conn, self.ticket.owner, effect, self.ticket.admission)

    def observe(self, generation):
        with self.pool.connection(timeout=2) as conn, conn.transaction():
            lock(conn, self.ticket.owner, exclusive=True)
            acquire(conn, self.units.ticket)
            row = self.row(conn)
            if not row or row['generation'] not in (None, generation):
                raise AuthorityRefused('original GCS generation changed')
            conn.execute(
                'UPDATE queue_provider_uploads SET generation=%s WHERE namespace=%s AND unit_id=%s AND attempt_token=%s',
                (generation, self.units.namespace, self.ticket.identity, self.ticket.attempt),
            )

    def publish(self, effect, generation):
        with self.pool.connection(timeout=2) as conn, conn.transaction():
            self.source(conn, pending=True)
            row = self.row(conn)
            if (
                not row
                or row['phase'] != 'registered'
                or row['generation'] != generation
                or str(row['effect_id']) != effect
            ):
                raise AuthorityRefused('GCS completion lost to a durable drain claim')

            def persist(connection):
                connection.execute(
                    "UPDATE queue_provider_uploads SET phase='published' WHERE namespace=%s "
                    'AND unit_id=%s AND attempt_token=%s',
                    (self.units.namespace, self.ticket.identity, self.ticket.attempt),
                )

            if not self.units.fence.complete(conn, self.ticket.owner, effect, self.ticket.admission, persist):
                raise AuthorityRefused('GCS COMPLETE privacy/source changed')


def uri(row):
    if row['generation'] is None:
        raise AuthorityRefused('positive original generation required')
    return f"gs://{row['bucket']}/{row['object_key']}#{row['generation']}"
