"""No-text projection of an exact source alias, under the assignment fence."""

from google.cloud import firestore

from database.batch_pipeline_source_reuse import current, SourceReuseUnavailable
from database.batch_pipeline_store import FirestoreTransaction
from database.batch_pipeline_projection_protocol import ProjectionReplay
from utils.batch_pipeline import source_reuse


def project_alias(store, item, binding, now, *, policy):
    @firestore.transactional
    def commit(transaction):
        session = store.session(item.segment_id, binding, now, policy=policy)
        session.allow_source_alias = True
        try:
            session.prepare(transaction)
        except ProjectionReplay:
            return True, False
        view = FirestoreTransaction(store.client, store.store.namespace, transaction)
        row = view.get('source_reuse', item.source_reuse_key)
        if not row or row.get('segment_id') == item.segment_id:
            if session.job.get('source_alias'):
                raise SourceReuseUnavailable('accepted alias source receipt unavailable')
            return False, False
        canonical = current(view, item, now)
        if canonical is None:
            source_reuse.observe('alias_wait')
            raise SourceReuseUnavailable('canonical source result not ready')
        expected = session.job.get('source_alias')
        if expected and expected.get('segment_id') != canonical['segment_id']:
            raise SourceReuseUnavailable('accepted alias canonical owner changed')
        ids = canonical['dependencies']
        session.guard(transaction, ids)
        # Read own artifact reservations before persist's first write. Racer
        # jobs already own their results; admission aliases own only a marker.
        refs = []
        from database.batch_pipeline_staging import artifact_id

        for uri in (item.audio_uri, session.job['result']['result_uri']):
            ref = store.ref('artifacts', artifact_id(item.segment_id, uri))
            artifact = ref.get(transaction=transaction).to_dict() or {}
            if (
                not artifact
                or artifact.get('owner_id') != item.owner_id
                or artifact.get('privacy_generation') != item.privacy_generation
                or artifact.get('erasure_requested')
            ):
                raise SourceReuseUnavailable('source alias artifact unavailable')
            refs.append(ref)
        entry = view.get('results', canonical['segment_id'])
        receipts = list((entry.get('projection_parts') or {}).values()) or [canonical['receipt']]
        outputs = sorted(
            {
                out['conversation_id']
                for receipt in receipts
                for out in receipt.get('size_rollover_outputs') or [receipt]
                if out.get('conversation_id')
            }
        )
        receipt = session.persist(transaction, superseded=True)
        receipt.update(
            disposition='source_alias',
            source_segment_id=canonical['segment_id'],
            conversation_id=outputs[0] if outputs else None,
            created=False,
            size_rollover_outputs=[{'conversation_id': cid, 'created': False} for cid in outputs],
            speech_seconds=0.0,
            audio_required=False,
            enrichment_required=False,
        )
        transaction.update(session.result_ref, {'projection': receipt, 'source_conversation_ids': ids})
        transaction.update(session.job_ref, {'source_conversation_ids': ids})
        for ref in refs:
            transaction.update(ref, {'source_conversation_ids': ids})
        return True, True

    aliased, changed = store.run(commit, policy=policy)
    if changed:
        source_reuse.observe('reused', item.duration_seconds)
        source_reuse.observe('duplicate_projection_refusal')
    return aliased
