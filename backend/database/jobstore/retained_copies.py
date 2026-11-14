"""First, fail-closed phase of mode-independent typed retained-copy erasure.

Real private FS transactions retire redundant views under the existing legal
hold/unit token. The original PG record remains the custodian, even after an
unknown FS/PG COMMIT or process exit. This is deliberately not a final purge
adapter: objects, original metadata, journal and cold-copy proofs remain gates.
No factory selects it, no clock grants authority, and no new TTL is assigned.
"""

from google.cloud import firestore

from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.fs_fence import handoff_ref
from database.jobstore.postgres_store import jsonb
from database.jobstore.provider_handoff import validate_provider_payload
from database.privacy_fence.protocol import conversation_key, lock, owner_key, row_dict


class RetainedCopiesPending(AuthorityRefused):
    """Do not advance legacy erasure or acknowledge all-copy completion."""


class RetainedCopies:
    def __init__(self, handoff):
        self.handoff = handoff

    def _terminal(self, conn, owner, conversation):
        lock(conn, owner, exclusive=True)
        epoch = conn.execute(
            'SELECT epoch FROM queue_authority WHERE namespace=%s', (self.handoff.ticket.namespace,)
        ).fetchone()
        if epoch != (self.handoff.ticket.value,):
            raise AuthorityRefused('retained-copy census requires the current PG queue epoch')
        p = row_dict(conn, 'SELECT * FROM privacy_owner_fence WHERE owner_key=%s', (owner,))
        if not p:
            raise AuthorityRefused('retained-copy erase requires an original terminal privacy fence')
        if conversation is None:
            if p['state'] not in {'purging', 'erased'}:
                raise AuthorityRefused('account erasure requires purging or erased P')
        elif p['state'] not in {'purging', 'erased'}:
            pc = conn.execute(
                'SELECT state FROM privacy_conversation_fence WHERE owner_key=%s AND conversation_key=%s',
                (owner, conversation_key(owner, conversation)),
            ).fetchone()
            if pc != ('deleted',):
                raise AuthorityRefused('conversation erasure requires terminal deleted PC')
        if conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE owner_key=%s LIMIT 1', (owner,)).fetchone():
            raise RetainedCopiesPending('original effects must drain before retained-copy erasure')
        return p

    def _manifest(self, row):
        intent = row['intent']
        binding = validate_provider_payload(intent['payload'])
        ns, identity = row['namespace'], row['identity']
        if binding.job_id != identity or owner_key(binding.owner_id) != row['owner_key']:
            raise AuthorityRefused('original recording ownership/census mismatch')
        paths = [
            handoff_ref(self.handoff.client, ns, 'provider_projection_' + table, identity + '/' + sid).path
            for sid in binding.segment_ids
            for table in ('jobs', 'results')
        ] + [handoff_ref(self.handoff.client, ns, 'provider_projection_owners', identity + '/' + row['owner_key']).path]
        return dict(
            unit_ids=list(binding.segment_ids),
            private_paths=paths,
            original_deadlines={
                sid: intent['payload']['jobs'][sid]['typed_provider']['custody_deadline'] for sid in binding.segment_ids
            },
            original_paths=[
                handoff_ref(self.handoff.client, ns, kind, identity).path
                for kind in ('intent', 'completion', 'receipt')
            ]
            + [self.handoff.client.collection(ns + '_intakes').document(identity).path],
            # These are outstanding obligations, never asserted absence or a
            # fabricated object/session certificate. Their original references
            # and attempt histories remain in PG until every outcome is known.
            outstanding=['original_objects', 'original_metadata', 'paid_attempts', 'journal', 'cold_copies'],
        )

    def inventory(self, uid, conversation=None):
        """Persist at most ten original recording censuses before deleting any copy.

        Full owner paging and the other cohorts remain a serving gate. Refuse
        oversized owner pages rather than silently acknowledge a partial census.
        This path does not consult the shadow/serving mode selector.
        """
        owner, ns = owner_key(uid), self.handoff.ticket.namespace
        with self.handoff.pool.connection() as conn, conn.transaction():
            self._terminal(conn, owner, conversation)
            rows = conn.execute(
                'SELECT identity FROM queue_handoffs WHERE namespace=%s AND owner_key=%s ORDER BY identity LIMIT 11',
                (ns, owner),
            ).fetchall()
            if len(rows) > 10:
                raise RetainedCopiesPending('bounded owner census needs continuation paging')
            selected = []
            for (identity,) in rows:
                row = self.handoff._required_row(conn, identity)
                if conversation is not None:
                    target = conversation_key(owner, conversation)
                    paid_targets = {t['conversation_key'] for t in row['admission']['privacy_targets']}
                    if conversation not in row['intent']['conversation_ids'] and target not in paid_targets:
                        continue
                manifest = self._manifest(row)
                digest = fingerprint(dict(intent=row['intent'], admission=row['admission']))
                old = row_dict(
                    conn,
                    'SELECT * FROM queue_retained_copy_custody WHERE namespace=%s AND recording_id=%s',
                    (ns, identity),
                )
                if old and (old['manifest'] != manifest or old['source_fingerprint'] != digest):
                    raise AuthorityRefused('original retained-copy census changed')
                if not old:
                    conn.execute(
                        'INSERT INTO queue_retained_copy_custody(namespace,recording_id,owner_key,source_fingerprint,manifest) '
                        'VALUES (%s,%s,%s,%s,%s)',
                        (ns, identity, owner, digest, jsonb(manifest)),
                    )
                selected.append((identity, manifest))
            return selected

    def retire_private(self, uid, identity, manifest, authority, *, conversation=None):
        """One bounded real FS COMMIT; missing copies are an idempotent replay.

        P/PC is terminal and cannot reopen. Actual FS queue epoch, account hold,
        destructive-unit token and original deletion intent are read inside the
        deleting transaction. No SQL pool slot/guard survives an FS RPC.
        """
        if authority.uid != uid or authority.client is not self.handoff.client:
            raise AuthorityRefused('retained-copy erasure requires the real customer unit authority')
        owner, ns = owner_key(uid), self.handoff.ticket.namespace
        with self.handoff.pool.connection() as conn, conn.transaction():
            self._terminal(conn, owner, conversation)
            census = row_dict(
                conn,
                'SELECT * FROM queue_retained_copy_custody WHERE namespace=%s AND recording_id=%s',
                (ns, identity),
            )
            if not census or census['owner_key'] != owner or census['manifest'] != manifest:
                raise AuthorityRefused('durable original census required before remote erasure')
        refs = [self.handoff.client.document(path) for path in manifest['private_paths']]

        @firestore.transactional
        def erase(transaction):
            authority.fence(transaction)
            self.handoff.authority.check(
                transaction, phases=('FS_OPEN', 'FS_CLOSING', 'BOTH_CLOSED', 'PG_OPEN', 'PG_CLOSING')
            )
            if conversation is not None:
                ref = self.handoff.client.document(f'users/{uid}/deleted_conversations/{conversation}')
                if not ref.get(transaction=transaction).exists:
                    raise AuthorityRefused('original conversation deletion intent required')
            else:
                ref = self.handoff.client.collection('batch_pipeline_privacy').document(owner)
                value = ref.get(transaction=transaction).to_dict() or {}
                if not value.get('purging'):
                    raise AuthorityRefused('original account privacy purge must still be active')
            # Read all before writes. Hash-derived private references belong to
            # the original recording; changed/foreign cursor contents refuse.
            values = [ref.get(transaction=transaction).to_dict() for ref in refs]
            for value in values:
                if value and value.get('owner_key') != owner:
                    raise AuthorityRefused('private retained-copy ownership changed')
            for ref in refs:
                transaction.delete(ref)

        erase(self.handoff.client.transaction())
        # Losing this COMMIT response is harmless: the immutable census and all
        # original references remain. The next run repeats the same FS deletes.
        with self.handoff.pool.connection() as conn, conn.transaction():
            self._terminal(conn, owner, conversation)
            conn.execute(
                "UPDATE queue_retained_copy_custody SET phase='private_erased' WHERE namespace=%s AND recording_id=%s",
                (ns, identity),
            )

    def before_legacy(self, uid, conversation, authority):
        """Explicit binding for the actual account/conversation erasure entrypoints.

        Never let the old shadow-only pass erase originals or declare completion
        while the new durable census still has unresolved remote copy families.
        """
        for identity, manifest in self.inventory(uid, conversation):
            self.retire_private(uid, identity, manifest, authority, conversation=conversation)
        raise RetainedCopiesPending('private copies retired; original/object/journal/cold-copy certification remains')
