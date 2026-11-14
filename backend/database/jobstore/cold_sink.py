"""Explicit customer-role conditional cold sink; never a queue or restore grant.

Original typed PG bodies are copied verbatim under opaque per-key references.
No runtime selects the copier. Unsupported families/legacy generations refuse;
final parity, cold-to-serving conversion and reverse-open remain separate gates.
"""

from google.cloud import firestore

from database import rpc_deadline
from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.batch_privacy_attempt import TOKEN_FIELD, token_version
from database.jobstore.authority import AuthorityRefused, fingerprint, replay_page
from database.jobstore.fs_fence import handoff_ref
from database.jobstore.postgres_store import jsonb
from database.jobstore.retained_manifest import original_manifest
from database.privacy_fence.protocol import lock, owner_key

FAMILIES = frozenset({'units', 'recordings', 'queue_custody', 'queue_handoffs', 'outbox'})


def logical_identity(family, identity):
    if family not in FAMILIES:
        raise AuthorityRefused('cold cohort adapter missing')
    if family == 'outbox':
        if set(identity) != {'kind', 'dedupe_key', 'generation'} or not all(identity.values()):
            raise AuthorityRefused('original logical outbox generation required')
    return identity


def recording_id(conn, namespace, family, identity):
    logical_identity(family, identity)
    if family == 'outbox':
        if identity['kind'] != 'project_conversation':
            raise AuthorityRefused('cold outbox cohort adapter missing')
        return identity['dedupe_key']
    if family == 'queue_handoffs':
        return identity['identity']
    if family == 'recordings':
        return identity['recording_id']
    key = identity['unit_id'] if family == 'units' else identity['identity']
    value = conn.execute(
        'SELECT recording_id FROM units WHERE namespace=%s AND unit_id=%s', (namespace, key)
    ).fetchone()
    if not value:
        raise AuthorityRefused('original unit custodian required for cold identity')
    return value[0]


class ColdSink:
    def __init__(self, handoff):
        self.handoff = handoff

    def ref(self, family, identity):
        logical_identity(family, identity)
        return handoff_ref(self.handoff.client, self.handoff.ticket.namespace, 'cold_' + family, fingerprint(identity))

    def barrier(self, identity):
        return self.handoff.ref('cold_recording_erasure', identity)

    def _context(self, row):
        seq, epoch, family, identity, operation, owner, _body = row
        if epoch != self.handoff.ticket.value or operation not in {'put', 'delete'}:
            raise AuthorityRefused('cold source epoch/operation refused')
        with self.handoff.pool.connection(timeout=2) as conn, conn.transaction():
            lock(conn, owner, exclusive=True)
            source = conn.execute(
                'SELECT seq,epoch,family,identity,operation,owner_key,body FROM queue_journal '
                'WHERE namespace=%s AND seq=%s',
                (self.handoff.ticket.namespace, seq),
            ).fetchone()
            if source != row:
                raise AuthorityRefused('cold source journal version/payload changed')
            recording = recording_id(conn, self.handoff.ticket.namespace, family, identity)
            original = self.handoff._required_row(conn, recording)
            if original['owner_key'] != owner or owner_key(original['intent']['uid']) != owner:
                raise AuthorityRefused('cold source original owner changed')
            if family == 'outbox' and identity['generation'] != original['admission']['admission_id']:
                raise AuthorityRefused('cold outbox does not belong to original admission')
            manifest = original_manifest(self.handoff, original)
            if self.ref(family, identity).path not in manifest['cold_paths']:
                raise AuthorityRefused('cold key outside original retained-copy census')
            digest = fingerprint(dict(intent=original['intent'], admission=original['admission']))
            existing = conn.execute(
                'SELECT source_fingerprint,manifest FROM queue_cold_copy_custody '
                'WHERE namespace=%s AND recording_id=%s',
                (self.handoff.ticket.namespace, recording),
            ).fetchone()
            if existing and existing != (digest, manifest):
                raise AuthorityRefused('original cold custody changed')
            if not existing:
                conn.execute(
                    'INSERT INTO queue_cold_copy_custody(namespace,recording_id,owner_key,source_fingerprint,manifest) '
                    'VALUES (%s,%s,%s,%s,%s)',
                    (self.handoff.ticket.namespace, recording, owner, digest, jsonb(manifest)),
                )
        return recording, original

    def _erased(self, transaction, recording, original, seq):
        value = self.barrier(recording).get(transaction=transaction).to_dict()
        if value:
            if (
                value.get('owner_key') != original['owner_key']
                or value.get('source_fingerprint')
                != fingerprint(dict(intent=original['intent'], admission=original['admission']))
                or value.get('epoch') != self.handoff.ticket.value
                or value.get('through', -1) < seq
            ):
                raise AuthorityRefused('cold erase barrier does not cover this original source version')
            return True
        return False

    def apply(self, row, *, timeout):
        with rpc_deadline.rpc_deadline(rpc_deadline.now() + timeout):
            rpc_deadline.bind_firestore_client(self.handoff.client)
            return self._apply(row)

    def _apply(self, row):
        """Real conditional FS COMMIT. Every response is a definitive per-row ack."""
        recording, original = self._context(row)
        seq, epoch, family, identity, operation, owner, body = row
        client = self.handoff.client

        @firestore.transactional
        def erased(transaction):
            self.handoff.authority.check(transaction, phases=('PG_OPEN', 'PG_CLOSING', 'BOTH_CLOSED'))
            return self._erased(transaction, recording, original, seq)

        # A terminal purge may acknowledge a covered old page without exporting
        # data or reopening privacy. No absence scan stands in for this marker.
        if erased(client.transaction()):
            return
        if operation != 'put' or body is None:
            raise AuthorityRefused('cold delete requires real destructive-unit custody')
        if body.get('namespace') != self.handoff.ticket.namespace:
            raise AuthorityRefused('cold body namespace changed')

        def admit(conn, admission):
            self.handoff._guard(conn, original)
            if any(
                admission[k] != original['admission'][k]
                for k in ('privacy_generation', 'privacy_change_seq', 'privacy_targets')
            ):
                raise AuthorityRefused('cold copy cannot adopt a restored original')

        admission = self.handoff.fence.admit_from_authority(
            client, original['intent']['uid'], original['intent']['conversation_ids'], admit
        )
        packet = dict(
            namespace=self.handoff.ticket.namespace,
            epoch=epoch,
            seq=seq,
            family=family,
            identity=identity,
            owner_key=owner,
            recording_id=recording,
            cold_only=True,
            body=body,
            source_fingerprint=fingerprint(row),
            original_deadlines={
                sid: job['typed_provider']['custody_deadline']
                for sid, job in original['intent']['payload']['jobs'].items()
            },
        )
        ref = self.ref(family, identity)

        @firestore.transactional
        def put(transaction):
            self.handoff.authority.check(transaction, phases=('PG_OPEN', 'PG_CLOSING', 'BOTH_CLOSED'))
            barrier = self._erased(transaction, recording, original, seq)
            token = client.collection('batch_pipeline_privacy').document(owner).get(transaction=transaction)
            previous = ref.get(transaction=transaction).to_dict()
            if barrier:
                return
            if token_version(token) is None or (token.to_dict() or {}).get(TOKEN_FIELD) != admission['privacy_token']:
                raise AuthorityRefused('cold copy privacy token changed')
            assert_batch_write_allowed(
                client,
                transaction,
                original['intent']['uid'],
                conversation_ids=original['intent']['conversation_ids'],
                expected_generation=original['admission']['fs_privacy_generation'],
                snapshots={},
            )
            if previous:
                if (
                    previous.get('owner_key') != owner
                    or previous.get('identity') != identity
                    or previous.get('recording_id') != recording
                    or previous.get('namespace') != self.handoff.ticket.namespace
                    or previous.get('cold_only') is not True
                ):
                    raise AuthorityRefused('cold destination ownership/identity changed')
                version = (previous.get('epoch', -1), previous.get('seq', -1))
                if version > (epoch, seq):
                    return
                if version == (epoch, seq):
                    if previous != packet:
                        raise AuthorityRefused('cold same-version payload changed')
                    return
            transaction.set(ref, packet)

        put(client.transaction())

    def page(self, *, limit=100):
        return replay_page(self.handoff.pool, self.handoff.ticket.namespace, self.apply, limit=limit)
