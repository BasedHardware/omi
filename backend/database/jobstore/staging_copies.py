"""Seal actual original staging custody before retiring redundant PG copies.

The original intake (including unique repair context), original staging rows,
all unpinned/late upload references and the PG census remain retained. No GCS
session status or final all-copy absence is inferred from these phase receipts.
"""

from datetime import datetime

from google.cloud import firestore
from psycopg import Error as PostgresError  # pyright: ignore[reportMissingImports]

from database import batch_pipeline_privacy_queries as queries
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.cold_purge import erase_recording
from database.jobstore.fs_fence import handoff_ref
from database.jobstore.staging_operations import StagingOperations, artifact_fingerprint
from database.privacy_fence.protocol import owner_key


class StagingCopies:
    def __init__(self, retained):
        self.retained, self.handoff = retained, retained.handoff
        self.operations = StagingOperations(retained)

    def _source(self, uid, identity, conversation):
        with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
            self.retained._terminal(conn, owner_key(uid), conversation)
            source = self.handoff._required_row(conn, identity)
            if source['owner_key'] != owner_key(uid):
                raise AuthorityRefused('staging original owner changed')
            return source

    def _fence(self, transaction, uid, authority, conversation, fs_generation):
        if authority.uid != uid or authority.client is not self.handoff.client:
            raise AuthorityRefused('staging requires original customer destructive-unit authority')
        authority.fence(transaction)
        self.handoff.authority.check(
            transaction, phases=('FS_OPEN', 'FS_CLOSING', 'BOTH_CLOSED', 'PG_OPEN', 'PG_CLOSING')
        )
        if conversation is not None:
            ref = self.handoff.client.document(f'users/{uid}/deleted_conversations/{conversation}')
            if not ref.get(transaction=transaction).exists:
                raise AuthorityRefused('staging original conversation deletion intent required')
        else:
            value = (
                self.handoff.client.collection('batch_pipeline_privacy')
                .document(owner_key(uid))
                .get(transaction=transaction)
                .to_dict()
                or {}
            )
            if type(fs_generation) is not int or not value.get('purging') or value.get('generation') != fs_generation:
                raise AuthorityRefused('staging exact account purge generation changed')

    def _intake(self, transaction, source):
        ref = self.handoff.client.collection(source['namespace'] + '_intakes').document(source['identity'])
        value = ref.get(transaction=transaction).to_dict()
        expected = source['intent']['payload']['intakes'].get(source['identity'])
        if not value or expected is None or {k: v for k, v in value.items() if k != 'repair_lineage'} != expected:
            raise AuthorityRefused('unique original intake missing or changed; no reconstruction')
        return ref, value

    def prepare(self, uid, identity, authority, *, conversation=None, fs_generation=None):
        source = self._source(uid, identity, conversation)
        marker = self.handoff.ref('staging_erasure', identity)
        units = self.retained._manifest(source)['unit_ids']

        @firestore.transactional
        def seal(transaction):
            self._fence(transaction, uid, authority, conversation, fs_generation)
            intake_ref, intake = self._intake(transaction, source)
            previous = marker.get(transaction=transaction).to_dict()
            artifacts, docs = [], []
            for segment in units:
                page = queries.segment_artifacts(self.handoff.client, source['namespace'], segment, transaction)
                if len(page) >= 256 or len(docs) + len(page) > 128:
                    raise AuthorityRefused('staging original census requires bounded continuation paging')
                docs.extend(page)
            for doc in sorted(docs, key=lambda doc: doc.id):
                value = doc.to_dict() or {}
                if (
                    value.get('owner_key') != owner_key(uid)
                    or value.get('owner_id') != uid
                    or value.get('segment_id') not in units
                    or value.get('privacy_generation') != source['admission']['fs_privacy_generation']
                    or value.get('kind') not in {'audio', 'result', 'results'}
                    or not isinstance(value.get('uri'), str)
                    or not value['uri']
                ):
                    raise AuthorityRefused('staging original artifact ownership/cohort changed')
                deadlines = {}
                for field in ('cleanup_after', 'expires_at', 'write_pending_until'):
                    deadline = value.get(field)
                    if deadline is not None and not isinstance(deadline, datetime):
                        raise AuthorityRefused('staging original deadline malformed')
                    deadlines[field] = deadline.isoformat() if deadline is not None else None
                artifacts.append(
                    dict(
                        key=doc.id,
                        path=doc.reference.path,
                        uri=value['uri'],
                        segment_id=value['segment_id'],
                        kind=value['kind'],
                        fingerprint=artifact_fingerprint(value),
                        original_deadlines=deadlines,
                        cold_path=handoff_ref(
                            self.handoff.client,
                            source['namespace'],
                            'cold_docs',
                            fingerprint(dict(tbl='artifacts', key=doc.id)),
                        ).path,
                    )
                )
            manifest = dict(
                namespace=source['namespace'],
                epoch=self.handoff.ticket.value,
                recording_id=identity,
                owner_key=owner_key(uid),
                source_fingerprint=fingerprint(dict(intent=source['intent'], admission=source['admission'])),
                intake_path=intake_ref.path,
                intake_fingerprint=fingerprint(intake),
                artifacts=artifacts,
                original_deadlines=self.retained._manifest(source)['original_deadlines'],
            )
            if previous and previous != manifest:
                raise AuthorityRefused('sealed original staging census changed')
            # Keep unique repair context and every upload capability in their
            # original document. This only narrows the existing erasure flag.
            for doc in docs:
                if (doc.to_dict() or {}).get('erasure_requested') is not True:
                    transaction.update(doc.reference, {'erasure_requested': True})
            if not previous:
                transaction.create(marker, manifest)
            return manifest

        manifest = seal(self.handoff.client.transaction())
        return self.operations.prepare(uid, identity, authority, manifest, conversation=conversation)

    def execute(self, uid, target, authority, *, conversation=None, fs_generation=None):
        try:
            return self._execute(uid, target, authority, conversation=conversation, fs_generation=fs_generation)
        except PostgresError as error:
            raise ConnectionError('staging PG custody/outcome unresolved') from error

    def _execute(self, uid, target, authority, *, conversation=None, fs_generation=None):
        manifest = self.operations.manifest(uid, target)
        source = self._source(uid, manifest['recording_id'], conversation)
        marker = self.handoff.ref('staging_erasure', manifest['recording_id'])

        @firestore.transactional
        def verify(transaction):
            self._fence(transaction, uid, authority, conversation, fs_generation)
            _, intake = self._intake(transaction, source)
            value = marker.get(transaction=transaction).to_dict()
            if value != manifest or fingerprint(intake) != manifest['intake_fingerprint']:
                raise AuthorityRefused('staging original FS custody changed before PG destructive unit')
            for artifact in manifest['artifacts']:
                value = self.handoff.client.document(artifact['path']).get(transaction=transaction).to_dict()
                if (
                    not value
                    or value.get('erasure_requested') is not True
                    or artifact_fingerprint(value) != artifact['fingerprint']
                ):
                    raise AuthorityRefused('staging unique FS reference missing or changed')

        verify(self.handoff.client.transaction())
        self.operations.execute(uid, target, authority, conversation=conversation)

    def retire_mirrors(self, uid, identity, authority, *, conversation=None, fs_generation=None):
        target = self.prepare(uid, identity, authority, conversation=conversation, fs_generation=fs_generation)
        source = self._source(uid, identity, conversation)
        manifest = self.retained._manifest(source)
        # The concrete staging census must exist before the cold journal can
        # resolve old artifact-copy keys. Keep the last PG custodian throughout.
        erase_recording(
            self.retained, uid, identity, manifest, authority, conversation=conversation, fs_generation=fs_generation
        )
        authority.remote(
            lambda: self.execute(uid, target, authority, conversation=conversation, fs_generation=fs_generation),
            target=target,
        )
        # DELETEs append to the committed prefix. Cover their real cold keys
        # too; never remove journal rows or infer a complete reverse sink.
        erase_recording(
            self.retained, uid, identity, manifest, authority, conversation=conversation, fs_generation=fs_generation
        )
