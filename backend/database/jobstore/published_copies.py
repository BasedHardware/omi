"""Published result originals, including publication before paid terminal COMMIT.

This is an original-copy phase receipt, never all-copy or remote C4 proof.
The immutable upload row, original deadline and journal remain custodians.
"""

import hashlib
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud import firestore

from database import rpc_deadline
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.erasure_operations import ErasureOperations
from database.jobstore.postgres_store import jsonb
from database.jobstore.result_upload_rows import uri
from database.jobstore.terminal_uploads import require_terminal
from database.privacy_fence.protocol import conversation_key, owner_key, row_dict
from utils.batch_pipeline.retention import delete_batch_object
from utils.batch_pipeline.upload_policy import UPLOAD_TIMEOUT


def payload(row):
    return dict(
        upload_hash=fingerprint(dict(row, admission_id=str(row['admission_id']), effect_id=str(row['effect_id']))),
        unit_id=row['unit_id'],
        attempt_token=row['attempt_token'],
        uri=uri(row) if row['generation'] is not None else f"gs://{row['bucket']}/{row['object_key']}",
    )


class PublishedCopies:
    def __init__(self, retained, *, storage_client=None):
        self.retained, self.handoff = retained, retained.handoff
        self.operations = ErasureOperations(retained)
        self.storage: Any = storage_client

    def _rows(self, uid, identity, conversation):
        with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
            self.retained._terminal(conn, owner_key(uid), conversation)
            source = self.handoff._required_row(conn, identity)
            manifest = self.retained._manifest(source)
            if (
                conversation is not None
                and conversation not in source['intent']['conversation_ids']
                and conversation_key(owner_key(uid), conversation)
                not in {t['conversation_key'] for t in source['admission']['privacy_targets']}
            ):
                raise AuthorityRefused('published original outside deleted conversation')
            rows = conn.execute(
                'SELECT unit_id FROM queue_provider_uploads WHERE namespace=%s AND recording_id=%s ORDER BY unit_id',
                (self.handoff.ticket.namespace, identity),
            ).fetchall()
            if len(rows) > len(manifest['unit_ids']):
                raise AuthorityRefused('published upload census exceeds original siblings')
            result = []
            for (unit,) in rows:
                row = row_dict(
                    conn,
                    'SELECT * FROM queue_provider_uploads WHERE namespace=%s AND unit_id=%s',
                    (self.handoff.ticket.namespace, unit),
                )
                if (
                    not row
                    or row['owner_key'] != owner_key(uid)
                    or str(row['admission_id']) != source['admission']['admission_id']
                    or unit not in manifest['unit_ids']
                    or row['original_deadline'] != manifest['original_deadlines'][unit]
                ):
                    raise AuthorityRefused('published original admission changed')
                if row['phase'] == 'fenced':
                    require_terminal(conn, row)
                elif row['phase'] != 'published':
                    raise ConnectionError('unresolved upload original remains in session custody')
                result.append(row)
            return result

    def _reference(self, row):
        reserved = f"gs://{row['bucket']}/{row['object_key']}"
        key = hashlib.sha256(f"{row['unit_id']}\0{reserved}".encode()).hexdigest()
        return self.handoff.client.collection(row['namespace'] + '_artifacts').document(key)

    def _check(self, uid, row, authority, conversation, fs_generation, *, erase=False):
        ref = self._reference(row)
        with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
            self.retained._terminal(conn, owner_key(uid), conversation)
            source = self.handoff._required_row(conn, row['recording_id'])['intent']['payload']['jobs'][row['unit_id']]
        expected = dict(
            owner_key=row['owner_key'],
            owner_id=uid,
            segment_id=row['unit_id'],
            uri=f"gs://{row['bucket']}/{row['object_key']}",
            kind='results',
            privacy_generation=source['privacy_generation'],
            capture_at=source['capture_at'],
            duration_seconds=source['duration_seconds'],
            provider_upload=dict(
                admission_id=str(row['admission_id']),
                attempt_token=row['attempt_token'],
                original_deadline=row['original_deadline'],
            ),
        )

        @firestore.transactional
        def check(transaction):
            authority.fence(transaction)
            self.handoff.authority.check(
                transaction, phases=('FS_OPEN', 'FS_CLOSING', 'BOTH_CLOSED', 'PG_OPEN', 'PG_CLOSING')
            )
            if conversation is not None:
                if (
                    not self.handoff.client.document(f'users/{uid}/deleted_conversations/{conversation}')
                    .get(transaction=transaction)
                    .exists
                ):
                    raise AuthorityRefused('published original deletion intent required')
            else:
                value = (
                    self.handoff.client.collection('batch_pipeline_privacy')
                    .document(owner_key(uid))
                    .get(transaction=transaction)
                    .to_dict()
                    or {}
                )
                if (
                    type(fs_generation) is not int
                    or not value.get('purging')
                    or value.get('generation') != fs_generation
                ):
                    raise AuthorityRefused('published original account purge generation changed')
            value = ref.get(transaction=transaction).to_dict()
            if value is not None and value != expected:
                raise AuthorityRefused('published original artifact reference changed')
            if erase:
                transaction.delete(ref)

        check(self.handoff.client.transaction())

    def _absent(self, uid, row):
        if row['generation'] is None:
            # Only a durable original terminal receipt can authorize this:
            # sticky 499/412 creates no owned generation to delete or adopt.
            with self.handoff.pool.connection(timeout=2) as conn:
                require_terminal(conn, row)
            return
        if self.storage is None:
            from utils.other.local_storage import create_storage_client

            self.storage = create_storage_client()
        try:
            delete_batch_object(uid, uri(row), storage_client=self.storage, namespace=row['namespace'])
            blob = self.storage.bucket(row['bucket']).blob(row['object_key'], generation=row['generation'])
            try:
                left = rpc_deadline.remaining()
                if left is not None and left <= 0:
                    raise TimeoutError('published original probe not sent: unit deadline passed')
                timeout = UPLOAD_TIMEOUT if left is None else tuple(min(t, left / 2) for t in UPLOAD_TIMEOUT)
                blob.reload(if_generation_match=row['generation'], timeout=timeout, retry=None)
            except NotFound:
                return
        except Exception:
            raise ConnectionError('published original erasure/absence unresolved') from None
        raise ConnectionError('published original generation still present')

    def retire(self, uid, identity, authority, *, conversation=None, fs_generation=None):
        for row in self._rows(uid, identity, conversation):
            body = payload(row)
            cohort = 'published' if row['phase'] == 'published' else 'fenced'
            for purpose in (cohort + '_object', cohort + '_reference'):
                with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
                    self.retained._terminal(conn, owner_key(uid), conversation)
                    done = conn.execute(
                        "SELECT 1 FROM queue_original_erasure_operations WHERE namespace=%s AND recording_id=%s AND purpose=%s AND payload=%s AND state='committed' LIMIT 1",
                        (row['namespace'], identity, purpose, jsonb(body)),
                    ).fetchone()
                if done:
                    continue
                self._check(uid, row, authority, conversation, fs_generation)
                target = self.operations.prepare(uid, identity, authority, purpose, body, conversation=conversation)
                if purpose == cohort + '_object':
                    authority.remote(lambda: self._absent(uid, row), target=body['uri'])
                else:
                    self._check(uid, row, authority, conversation, fs_generation, erase=True)
                authority.remote(
                    lambda: self.operations.finish(uid, target, authority, conversation=conversation), target=target
                )
