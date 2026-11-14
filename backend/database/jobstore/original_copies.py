"""Concrete original-object and FS metadata erasure, still without cold proof.

The production retention delete is generation pinned. Transport is injectable
for isolated tests; this does not qualify a real GCS terminal-session adapter.
All original PG records/journal remain protected by the retained-copy guard.
"""

from urllib.parse import urlsplit

from google.cloud import firestore

from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.erasure_operations import ErasureOperations
from database.jobstore.retained_copies import RetainedCopiesPending
from database.jobstore.postgres_store import jsonb
from database.privacy_fence.protocol import owner_key
from utils.batch_pipeline.retention import delete_batch_object


class OriginalCopies:
    def __init__(self, retained, *, storage_client=None):
        self.retained, self.handoff = retained, retained.handoff
        self.operations = ErasureOperations(retained)
        self.storage_client = storage_client

    def _plan(self, uid, identity, conversation):
        with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
            self.retained._terminal(conn, owner_key(uid), conversation)
            row = self.handoff._required_row(conn, identity)
            completion = row['completion']
            units = (completion or {}).get('units', [])
            binding = self.retained._manifest(row)
            if (
                row['owner_key'] != owner_key(uid)
                or not completion
                or fingerprint(completion) != row['completion_hash']
                or [u['unit_id'] for u in units] != binding['unit_ids']
                or any(u['state'] != 'result_ready' for u in units)
            ):
                raise RetainedCopiesPending('original erasure certification remains: complete ordinary source required')
            uris = sorted(
                {uri for unit in units for uri in (unit['source']['audio_uri'], unit['result']['result_uri'])}
            )
            # Validate the ENTIRE census before sending even the first delete.
            # Never resolve an unpinned name by observing its current generation.
            if any(
                urlsplit(uri).scheme != 'gs'
                or not urlsplit(uri).fragment.isdecimal()
                or int(urlsplit(uri).fragment) <= 0
                for uri in uris
            ):
                raise RetainedCopiesPending('original erasure certification remains: original generation pins required')
            return row, binding, uris

    def _done(self, uid, identity, purpose, payload, conversation):
        with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
            self.retained._terminal(conn, owner_key(uid), conversation)
            return bool(
                conn.execute(
                    "SELECT 1 FROM queue_original_erasure_operations WHERE namespace=%s AND recording_id=%s "
                    "AND purpose=%s AND state='committed' AND payload=%s LIMIT 1",
                    (self.handoff.ticket.namespace, identity, purpose, jsonb(payload)),
                ).fetchone()
            )

    def retire(self, uid, identity, authority, *, conversation=None, fs_generation=None):
        row, manifest, uris = self._plan(uid, identity, conversation)
        if conversation is None and type(fs_generation) is not int:
            raise AuthorityRefused('original account FS purge generation required')
        for uri in uris:
            payload = dict(uri=uri, completion_hash=row['completion_hash'])
            if self._done(uid, identity, 'object', payload, conversation):
                continue
            target = self.operations.prepare(uid, identity, authority, 'object', payload, conversation=conversation)
            authority.remote(lambda: delete_batch_object(uid, uri, storage_client=self.storage_client), target=uri)
            authority.remote(
                lambda: self.operations.finish(uid, target, authority, conversation=conversation), target=target
            )
        # Original intake repair context is deliberately outside the PG intent.
        # Keep that unique custodian until its own complete reference adapter
        # is qualified; do not copy it into PG or discard it on this proof.
        metadata = dict(paths=manifest['original_paths'][:3], completion_hash=row['completion_hash'], uris=uris)
        if self._done(uid, identity, 'metadata', metadata, conversation):
            return
        target = self.operations.prepare(
            uid,
            identity,
            authority,
            'metadata',
            metadata,
            conversation=conversation,
        )
        refs = [self.handoff.client.document(path) for path in metadata['paths']]

        @firestore.transactional
        def erase(transaction):
            # This COMMIT, not an earlier observation, fences a paused old unit.
            authority.fence(transaction)
            self.handoff.authority.check(
                transaction, phases=('FS_OPEN', 'FS_CLOSING', 'BOTH_CLOSED', 'PG_OPEN', 'PG_CLOSING')
            )
            if conversation is not None:
                intent = self.handoff.client.document(f'users/{uid}/deleted_conversations/{conversation}')
                if not intent.get(transaction=transaction).exists:
                    raise AuthorityRefused('original conversation deletion intent required')
            else:
                intent = self.handoff.client.collection('batch_pipeline_privacy').document(owner_key(uid))
                privacy = intent.get(transaction=transaction).to_dict() or {}
                if not privacy.get('purging') or privacy.get('generation') != fs_generation:
                    raise AuthorityRefused('original account purge must still be active')
            values = [ref.get(transaction=transaction).to_dict() for ref in refs]
            source, completion, receipt = values
            if source and source != dict(intent=row['intent'], fingerprint=row['fingerprint']):
                raise AuthorityRefused('original FS source changed')
            for value in (completion, receipt):
                if value and any(
                    value.get(k) != row[k] for k in ('namespace', 'identity', 'fingerprint', 'completion_hash')
                ):
                    raise AuthorityRefused('original FS completion/receipt changed')
            for ref in refs:
                transaction.delete(ref)

        erase(self.handoff.client.transaction())
        authority.remote(
            lambda: self.operations.finish(uid, target, authority, conversation=conversation), target=target
        )
        # No final retirement: the journal prefix, cold/reverse sinks, staging
        # and terminal upload sessions still require actual independent proof.
