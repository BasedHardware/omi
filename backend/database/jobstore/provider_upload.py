"""Explicit ordinary paid-result ArtifactStore binding. No runtime selects it.

Legacy/native/audio/recovery upload policy stays unchanged. This result-only
adapter never creates FS runnable jobs, retries a PUT or adopts a restored paid
admission. Original references/deadlines remain durable through unknown outcomes.
"""

from contextlib import contextmanager
import hashlib
import math
from types import SimpleNamespace

from google.cloud import firestore
from psycopg import Error as PostgresError  # pyright: ignore[reportMissingImports]

from database import rpc_deadline
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyBlocked
from database.batch_privacy_attempt import TOKEN_FIELD, token_version
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.gcs_sink import GCSSink
from database.jobstore.result_upload_rows import ResultUploadRows, uri
from database.privacy_fence import FenceRefused
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.upload_policy import UPLOAD_TIMEOUT


class ProviderUpload:
    def __init__(self, ticket, storage_client, *, lease_seconds, timeout=UPLOAD_TIMEOUT):
        if not isinstance(lease_seconds, (int, float)) or not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError('explicit finite GCS effect lease required')
        self.ticket, self.handoff, self.lease_seconds = ticket, ticket.handoff, lease_seconds
        self.rows = ResultUploadRows(ticket)
        self.sink = GCSSink(self.handoff, storage_client, timeout=timeout)
        self.transport = self.sink.transport
        self.client, self.namespace = self.handoff.client, self.handoff.ticket.namespace
        rpc_deadline.bind_firestore_client(self.client)

    def artifacts(self, bucket, master_secret):
        # Customer/storage role composition, never in the provider worker's
        # default dependency closure or selected by an environment flag.
        from utils.batch_pipeline.artifact_policy import create_artifact_store

        return create_artifact_store(
            SimpleNamespace(client=self.client, namespace=self.namespace),
            self.transport.client,
            bucket,
            master_secret,
            provider_upload=self,
        )

    def _item(self, item):
        expected = {key: self.ticket.source.get(key) for key in item.to_dict()}
        if fingerprint(expected) != fingerprint(item.to_dict()) or item.shadow:
            raise AuthorityRefused('result upload differs from original paid source')

    def _admission(self, item):
        self._item(item)

        def admit(conn, current):
            self.rows.source(conn)
            if any(
                current[key] != self.ticket.admission[key]
                for key in ('privacy_generation', 'privacy_change_seq', 'privacy_targets')
            ):
                raise AuthorityRefused('result upload cannot adopt a restored paid admission')

        return self.handoff.fence.admit_from_authority(
            self.client,
            item.owner_id,
            self.ticket.conversation_ids,
            admit,
        )

    def _privacy(self, transaction, item, admission, *, read_budget=None):
        self.handoff.authority.check(transaction, phases=('PG_OPEN',))
        token = (
            self.client.collection('batch_pipeline_privacy')
            .document(self.ticket.owner)
            .get(
                transaction=transaction,
                **(dict(timeout=read_budget.timeout(10), retry=None) if read_budget is not None else {}),
            )
        )
        if token_version(token) is None or (token.to_dict() or {}).get(TOKEN_FIELD) != admission['privacy_token']:
            raise AuthorityRefused('result upload writing-transaction token changed')
        loaded = {}
        generation = assert_batch_write_allowed(
            self.client,
            transaction,
            item.owner_id,
            conversation_ids=self.ticket.conversation_ids,
            expected_generation=item.privacy_generation,
            snapshots=loaded,
            read_budget=read_budget,
        )
        return ProtectionContext(loaded['user'].get('data_protection_level', 'enhanced'), generation)

    def authorize(self, item):
        admission = self._admission(item)

        @firestore.transactional
        def read(transaction):
            return self._privacy(transaction, item, admission)

        return read(self.client.transaction())

    def authorize_read(self, item, *, read_budget):
        from database.batch_pipeline_reads import read_snapshot

        read_budget.timeout(10)
        # Preserve the caller's single-attempt object-authorizing snapshot and
        # deadline. G2 admission retains its existing bounded A1/walk/A2 policy;
        # all of its FS RPCs also honour this same caller deadline. The original
        # paid source remains immutable and is checked again after object I/O.
        with rpc_deadline.rpc_deadline(read_budget.deadline):
            admission = self._admission(item)
            result = read_snapshot(
                SimpleNamespace(client=self.client, namespace=self.namespace),
                lambda tx: self._privacy(tx.transaction, item, admission, read_budget=read_budget),
                read_budget,
            )
            read_budget.timeout(10)
            return result

    @contextmanager
    def writer_scope(self):
        from database.batch_privacy_write_fence import g2_coordinator
        from database.privacy_fence.interceptor import Coordinator

        token = g2_coordinator.set(Coordinator(self.client, self.handoff.fence))
        try:
            yield
        finally:
            g2_coordinator.reset(token)

    def _register_reference(self, item, row, context):
        admission = self._admission(item)
        reserved = f"gs://{row['bucket']}/{row['object_key']}"
        identity = hashlib.sha256(f'{item.segment_id}\0{reserved}'.encode()).hexdigest()
        ref = self.client.collection(self.namespace + '_artifacts').document(identity)
        expected = dict(
            owner_key=self.ticket.owner,
            owner_id=item.owner_id,
            segment_id=item.segment_id,
            uri=reserved,
            kind='results',
            privacy_generation=context.generation,
            capture_at=item.capture_at,
            duration_seconds=item.duration_seconds,
            provider_upload=dict(
                admission_id=str(row['admission_id']),
                attempt_token=row['attempt_token'],
                original_deadline=row['original_deadline'],
            ),
        )

        @firestore.transactional
        def register(transaction):
            if self._privacy(transaction, item, admission) != context:
                raise AuthorityRefused('original result protection changed')
            old = ref.get(transaction=transaction).to_dict()
            if old is not None and old != expected:
                raise AuthorityRefused('original result artifact reference changed')
            if old is None:
                transaction.create(ref, expected)

        with self.writer_scope():
            register(self.client.transaction())

    def write(self, store, item, kind, body, *, result_key=None):
        if kind != 'results' or result_key is not None:
            raise AuthorityRefused('ordinary result-only session adapter; cohort binding required')
        self._item(item)
        try:
            context = self.authorize(item)
            row = self.rows.prepare(store, hashlib.sha256(body).hexdigest())
            if row['phase'] == 'published':
                return uri(row)
            self._register_reference(item, row, context)
            sealed = store._seal(item, kind, context, body)
            blob = store.bucket.blob(row['object_key'])
            session = self.transport.create(blob, len(sealed))
            effect = self.rows.register(session, row, len(sealed), lease_seconds=self.lease_seconds)
            self.authorize(item)
            self.rows.start(effect)
            # H-25: the one PUT is next on this stack after START COMMIT.
            generation = self.transport.put(session, sealed)
            self.rows.observe(generation)
            self.authorize(item)
            self.rows.publish(effect, generation)
            return f"gs://{row['bucket']}/{row['object_key']}#{generation}"
        except PostgresError as error:
            raise ConnectionError('result upload PG outcome unresolved; original custody retained') from error
        except (FenceRefused, AuthorityRefused, BatchPrivacyBlocked):
            # An actual legal-hold destructive unit must be supplied by the
            # drain/purge runner before cleanup. Never erase from the worker on
            # a privacy exception or turn that exception into another paid send.
            raise
