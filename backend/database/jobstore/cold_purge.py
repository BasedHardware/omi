"""Real cold FS erasure and durable suppression, not final all-copy retirement.

The retained original PG custodian owns these references/deadlines. A terminal
P/PC, drained effects, hold/unit token and actual namespace epoch fence every
erase. Journal source rows remain intact; no parity certificate is fabricated.
"""

from google.cloud import firestore

from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.cold_sink import ColdSink, recording_id
from database.jobstore.staging_census import cold_paths
from database.jobstore import upload_cold_custody
from database.privacy_fence.protocol import owner_key


def erase_recording(retained, uid, identity, manifest, authority, *, conversation=None, fs_generation=None):
    handoff, owner = retained.handoff, owner_key(uid)
    if authority.uid != uid or authority.client is not handoff.client:
        raise AuthorityRefused('cold erasure requires original destructive-unit authority')
    sink = ColdSink(handoff)
    with handoff.pool.connection(timeout=2) as conn, conn.transaction():
        retained._terminal(conn, owner, conversation)
        original = handoff._required_row(conn, identity)
        if original['owner_key'] != owner or retained._manifest(original) != manifest:
            raise AuthorityRefused('cold purge original census changed')
        sink.retain_original(conn, original)
        paths = manifest['cold_paths'] + cold_paths(conn, handoff.ticket.namespace, identity)
        rows = conn.execute(
            'SELECT seq,epoch,family,identity,operation,owner_key,body FROM queue_journal '
            'WHERE namespace=%s AND owner_key=%s ORDER BY seq LIMIT 1001',
            (handoff.ticket.namespace, owner),
        ).fetchall()
        if len(rows) > 1000:
            raise AuthorityRefused('cold owner journal census needs continuation paging')
        keys, uploads, through = {}, {}, 0
        for row in rows:
            # Unknown/shared families refuse before any deletion. Never infer
            # a missing cold copy from the serving/shadow mode selector.
            recording = recording_id(conn, handoff.ticket.namespace, row[2], row[3])
            if recording == identity:
                if row[2] == upload_cold_custody.FAMILY:
                    # Census the original capability's cold key even when no
                    # copier has ever run. The original manifest stays intact.
                    path = upload_cold_custody.retain(conn, handoff, original, row[3], row[6])
                    paths.append(path)
                    uploads[path] = upload_cold_custody.descriptor(row[6])
                key = sink.ref(row[2], row[3]).path
                if key not in paths:
                    raise AuthorityRefused('cold journal key outside original retained-copy census')
                keys[key] = dict(family=row[2], identity=row[3], seq=row[0])
                through = max(through, row[0])
        if len(keys) > 399:
            raise AuthorityRefused('cold recording exceeds bounded FS erasure chunk')
        digest = fingerprint(dict(intent=original['intent'], admission=original['admission']))
    barrier_ref = sink.barrier(identity)
    refs = [handoff.client.document(path) for path in sorted(keys)]
    receipt = dict(
        namespace=handoff.ticket.namespace,
        epoch=handoff.ticket.value,
        recording_id=identity,
        owner_key=owner,
        source_fingerprint=digest,
        through=through,
        keys=keys,
        original_deadlines=manifest['original_deadlines'],
        cold_only=True,
    )

    @firestore.transactional
    def erase(transaction):
        authority.fence(transaction)
        handoff.authority.check(transaction, phases=('FS_OPEN', 'FS_CLOSING', 'BOTH_CLOSED', 'PG_OPEN', 'PG_CLOSING'))
        if conversation is not None:
            intent = handoff.client.document(f'users/{uid}/deleted_conversations/{conversation}')
            if not intent.get(transaction=transaction).exists:
                raise AuthorityRefused('cold conversation deletion intent required')
        else:
            intent = handoff.client.collection('batch_pipeline_privacy').document(owner)
            privacy = intent.get(transaction=transaction).to_dict() or {}
            if (
                type(fs_generation) is not int
                or not privacy.get('purging')
                or privacy.get('generation') != fs_generation
            ):
                raise AuthorityRefused('cold account purge generation changed')
        old = barrier_ref.get(transaction=transaction).to_dict()
        values = [ref.get(transaction=transaction).to_dict() for ref in refs]
        if old and (
            old.get('source_fingerprint') != digest or old.get('owner_key') != owner or old.get('through', -1) > through
        ):
            raise AuthorityRefused('cold erasure barrier changed or census regressed')
        for ref, value in zip(refs, values):
            if value and (
                value.get('owner_key') != owner or value.get('recording_id') != identity or not value.get('cold_only')
            ):
                raise AuthorityRefused('cold destination owner/recording changed')
            if (
                value
                and ref.path in uploads
                and (
                    value.get('namespace') != handoff.ticket.namespace
                    or value.get('epoch') != handoff.ticket.value
                    or type(value.get('seq')) is not int
                    or value['seq'] > keys[ref.path]['seq']
                    or value.get('identity') != keys[ref.path]['identity']
                    or value.get('family') != upload_cold_custody.FAMILY
                    or not isinstance(value.get('body'), dict)
                    or set(value['body']) != upload_cold_custody.FIELDS
                    or upload_cold_custody.descriptor(value['body']) != uploads[ref.path]
                )
            ):
                raise AuthorityRefused('upload cold destination version/source changed')
        for ref in refs:
            transaction.delete(ref)
        transaction.set(barrier_ref, receipt)

    erase(handoff.client.transaction())
    return receipt
