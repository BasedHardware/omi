"""No-text projection of an exact source alias, under the assignment fence."""

from dataclasses import replace

from google.cloud import firestore

from database.batch_pipeline_source_reuse import current, SourceReuseUnavailable, TABLE, receipt_id
from database.batch_pipeline_store import FirestoreTransaction
from database.batch_pipeline_projection_protocol import ProjectionReplay
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.observability.fallback import record_fallback
from utils.batch_pipeline import source_reuse


def project_alias(store, item, binding, now, *, policy):
    @firestore.transactional
    def commit(transaction):
        view = FirestoreTransaction(store.client, store.store.namespace, transaction)
        job = view.get('jobs', item.segment_id)
        if job.get('source_alias_fallback'):
            if job.get('state') != 'committed':
                raise SourceReuseUnavailable('source fallback processing pending')
            return False, False  # Freshly computed own audio uses ordinary projection/accounting.
        expected = job.get('source_alias')
        row = view.get(TABLE, receipt_id(item.source_reuse_key))
        # Another accepted alias already reserved this fallback range. Do not
        # start a second paid fallback while its result is still pending.
        successor = bool(expected and row.get('fallback_from') == expected.get('segment_id'))
        canonical = None
        try:
            canonical = current(
                view, replace(item, source_conversation_ids=()) if successor else item, now, require_artifacts=False
            )
        except BatchPrivacyBlocked:
            if not expected:
                raise
            # The fallback below independently checks the alias's own account,
            # generation and upload deletion fences before any queue write.
        session = store.session(item.segment_id, binding, now, policy=policy)
        session.allow_source_alias = True
        session.detach_source_alias = successor
        if expected and canonical is None and not successor:
            from database.batch_pipeline_source_fallback import enqueue

            session.detach_source_alias = True
            session.prepare(transaction, replay=False)
            enqueue(session, view, item, now)
            return True, 'fallback'
        try:
            session.prepare(transaction)
        except ProjectionReplay:
            return True, False
        if not row or row.get('segment_id') == item.segment_id:
            return False, False
        if canonical is None:
            source_reuse.observe('alias_wait')
            raise SourceReuseUnavailable('canonical source result not ready')
        if not expected and not source_reuse.enabled():
            source_reuse.observe('alias_refusal')
            raise SourceReuseUnavailable('new source projection aliases are disabled')
        if expected and expected.get('segment_id') != canonical['segment_id'] and not successor:
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
            transaction.update(ref, {'source_conversation_ids': ids, 'conversation_ids': ids})
        return True, True

    aliased, changed = store.run(commit, policy=policy)
    if changed == 'fallback':
        source_reuse.observe('fallback', item.duration_seconds)
        record_fallback(
            component='sync_dispatch',
            from_mode='source_alias',
            to_mode='paid_audio',
            reason='unavailable',
            outcome='degraded',
        )
        raise SourceReuseUnavailable('source fallback enqueued')
    if changed:
        source_reuse.observe('reused', item.duration_seconds)
    return aliased
