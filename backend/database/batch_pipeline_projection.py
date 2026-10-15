"""Result-log projection receipts sharing the legacy assignment transaction.

No transcript bodies are copied into scheduler metadata. Durable completion is
separate from the Redis client projection, and can repair a lost Redis reply.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.sync_ledger import (
    batch_projection_ledger_owner_matches,
    sync_content_ledger_ref,
    is_valid_completed_sync_content_result,
    LEDGER_RETENTION_DAYS,
)
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.capture import chunk_identity


class ProjectionBlocked(RuntimeError):
    """A predecessor, immutable binding, or ledger owner is not ready."""


class ProjectionReplay(Exception):
    def __init__(self, receipt: dict):
        self.receipt = receipt


def normalized_binding(raw: dict[str, Any]) -> ProjectionBinding:
    values: dict[str, Any] = {**raw, 'segment_ids': tuple(raw['segment_ids'])}
    return ProjectionBinding(**values)


class ProjectionStore:
    def __init__(self, store: FirestoreStore):
        self.store = store

    @property
    def client(self):
        return self.store.client

    def ref(self, table: str, key: str):
        return self.client.collection(f'{self.store.namespace}_{table}').document(key)

    def read(self, segment_id: str) -> tuple[dict[str, Any], dict[str, Any], ProjectionBinding]:
        # This snapshot is a fetch hint only. Every mutation rereads it atomically.
        job = self.ref('jobs', segment_id).get().to_dict() or {}
        entry = self.ref('results', segment_id).get().to_dict() or {}
        if not entry or not job.get('projection_binding'):
            raise ProjectionBlocked('committed result and durable intake binding required')
        return job, entry, normalized_binding(job['projection_binding'])

    def session(self, segment_id: str, binding: ProjectionBinding, now: float):
        return ProjectionSession(self, segment_id, binding, now)

    def ready(self, segment_id: str, binding: ProjectionBinding, now: float) -> dict:
        """Acknowledge a replayable post-persist mark; never append again."""

        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now)
            session.prepare(transaction, replay=False)
            receipt = dict(session.entry.get('projection') or {})
            if not receipt:
                raise ProjectionBlocked('projection must persist before enrichment acknowledgment')
            receipt['state'] = 'ready'
            transaction.update(session.result_ref, {'projection': receipt, 'projection_state': 'ready'})
            return receipt

        return self.run(commit)

    def check(self, session):
        @firestore.transactional
        def read(transaction):
            session.prepare(transaction)

        self.run(read)

    def acknowledge(self, segment_id: str, binding: ProjectionBinding, now: float):
        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now)
            session.prepare(transaction, replay=False)
            if session.ledger.get('status') != 'completed':
                raise ProjectionBlocked('client publication preceded durable completion')
            transaction.update(session.result_ref, {'projection_state': 'completed'})

        self.run(commit)

    def status(self, uid: str, content_id: str) -> dict | None:
        @firestore.transactional
        def read(transaction):
            assert_batch_write_allowed(self.client, transaction, uid)
            row = sync_content_ledger_ref(self.client, uid, content_id).get(transaction=transaction).to_dict() or {}
            if row.get('dispatch_protocol') != 'batch_v1':
                return None
            result = row.get('result')
            completed = row.get('status') == 'completed' and is_valid_completed_sync_content_result(result)
            return {
                'job_id': row['job_id'],
                'status': 'completed' if completed else 'processing',
                'result': result if completed else None,
            }

        return self.run(read)

    def mark_enrichment(self, segment_id: str, binding: ProjectionBinding, now: float, canonical: str, language: str):
        from utils.sync import reprocess

        def mutate(document_id, operation):
            @firestore.transactional
            def commit(transaction):
                session = self.session(segment_id, binding, now)
                session.prepare(transaction, replay=False)
                session.guard(transaction, [canonical])
                receipt = dict(session.entry.get('projection') or {})
                ref = self.client.collection(reprocess.COLLECTION).document(document_id)
                snapshot = ref.get(transaction=transaction)
                old = snapshot.to_dict() if snapshot.exists else None
                if receipt.get('state') == 'ready':
                    return old or {}, True
                row, result = operation(old)
                # The enrichment obligation and its exactly-once projection
                # receipt commit together, fenced against account deletion.
                transaction.set(ref, row)
                receipt.update(state='ready', conversation_id=canonical)
                transaction.update(session.result_ref, {'projection': receipt, 'projection_state': 'ready'})
                return result

            return self.run(commit)

        reprocess.mark(binding.owner_id, canonical, language, now=now, mutate=mutate)

    def run(self, operation):
        # Same bounded opt-in read-contention retry as legacy sync (#21680).
        import os
        from database._client import run_transactional
        from database.firestore_transaction_retry import run_with_transaction_contention_retry

        if os.getenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'false').strip().lower() != 'true':
            return run_transactional(self.client, operation)
        return run_with_transaction_contention_retry(
            self.client.transaction,
            operation,
            operation_name='batch_projection',
        )

    def prepare_accounting(self, binding: ProjectionBinding, now: float) -> dict | None:
        """Resolve usage attribution outside the retryable completion transaction."""
        import math

        seconds = 0.0
        source = 'sync_backfill'
        for sid in binding.segment_ids:
            entry = self.ref('results', sid).get().to_dict() or {}
            if entry.get('projection_state') == 'erased':
                continue
            receipt = entry.get('projection') or {}
            if receipt.get('state') != 'ready':
                return None
            value = receipt.get('speech_seconds')
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ProjectionBlocked('validated speech accounting receipt required')
            seconds += value
            job = self.ref('jobs', sid).get().to_dict() or {}
            if job.get('priority') == 0:
                source = 'sync_fresh'
        stamp = datetime.fromtimestamp(now, timezone.utc)
        updates = {}
        ledger = sync_content_ledger_ref(self.client, binding.owner_id, binding.content_id).get().to_dict() or {}
        if int(seconds) > 0 and ledger.get('status') != 'completed':
            from database.llm_usage import resolve_usage_plan_id
            from database.hourly_usage_updates import prepare_hourly_usage_updates

            updates = prepare_hourly_usage_updates(
                stamp,
                {'transcription_seconds': int(seconds), 'speech_seconds': int(seconds)},
                resolve_usage_plan_id(binding.owner_id, firestore_client=self.client),
                usage_metadata={'funding': 'omi', 'provider': 'parakeet', 'source': 'sync_v2'},
            )
        return {
            'seconds': seconds,
            'source': source,
            'updates': updates,
            'hour': f'{stamp.year}-{stamp.month:02d}-{stamp.day:02d}-{stamp.hour:02d}',
            'completed': ledger.get('status') == 'completed',
        }

    def complete(self, segment_id: str, binding: ProjectionBinding, now: float, accounting: dict) -> dict | None:
        """Complete only after every bound sibling persisted and marked enrichment."""

        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now)
            session.prepare(transaction, replay=False)
            receipts = []
            live_siblings = []
            erased_count = 0
            for sibling in binding.segment_ids:
                job = self.ref('jobs', sibling).get(transaction=transaction).to_dict() or {}
                entry = self.ref('results', sibling).get(transaction=transaction).to_dict() or {}
                if entry.get('projection_state') == 'erased':
                    if entry.get('owner_key') != owner_key(binding.owner_id) or entry.get('segment_id') != sibling:
                        raise ProjectionBlocked('erased sibling owner mismatch')
                    receipts.append({'state': 'ready', 'conversation_id': None, 'created': False})
                    erased_count += 1
                    continue
                live_siblings.append(sibling)
                if not job.get('projection_binding') or normalized_binding(job['projection_binding']) != binding:
                    raise ProjectionBlocked('sibling binding mismatch')
                receipt = entry.get('projection') or {}
                if receipt.get('state') != 'ready':
                    return None
                receipts.append(receipt)
            # Earlier receipt IDs can have become bridge donors. Follow the
            # same server redirects, retaining only visible canonical IDs.
            mapped = []
            for receipt in receipts:
                cid = receipt.get('conversation_id')
                original_id = cid
                seen = set()
                while cid:
                    if cid in seen or len(seen) >= 128:
                        raise ProjectionBlocked('projection redirect cycle or bound exceeded')
                    seen.add(cid)
                    row = (
                        self.client.collection('users')
                        .document(binding.owner_id)
                        .collection('conversations')
                        .document(cid)
                        .get(transaction=transaction)
                        .to_dict()
                        or {}
                    )
                    if not row or (row.get('deleted') and not row.get('sync_merged_into')):
                        raise ProjectionBlocked('projected conversation deleted')
                    if not row.get('sync_merged_into'):
                        break
                    cid = row['sync_merged_into']
                if cid:
                    mapped.append((cid, receipt['created'] and cid == original_id))
            new = sorted({cid for cid, created in mapped if created})
            updated = sorted({cid for cid, created in mapped if not created})
            # Re-read canonical deletion fences before publishing any visible IDs.
            session.guard(transaction, (*new, *updated))
            result = {
                'new_memories': new,
                'updated_memories': updated,
                'failed_segments': 0,
                'total_segments': len(receipts),
                'errors': [],
                'outcome': 'success' if new or updated or erased_count else 'expected_silence',
            }
            if session.ledger.get('status') == 'completed':
                old = session.ledger.get('result')
                if not is_valid_completed_sync_content_result(old):
                    raise ProjectionBlocked('invalid existing ledger completion')
                return old
            seconds = sum(receipt.get('speech_seconds', 0.0) for receipt in receipts)
            if seconds != accounting['seconds']:
                raise ProjectionBlocked('speech accounting changed during completion')
            if session.ledger.get('usage_committed_at') is None:
                if accounting['updates']:
                    usage_ref = (
                        self.client.collection('users')
                        .document(binding.owner_id)
                        .collection('hourly_usage')
                        .document(accounting['hour'])
                    )
                    transaction.set(usage_ref, accounting['updates'], merge=True)
                transaction.update(
                    session.ledger_ref, {'usage_committed_at': datetime.fromtimestamp(now, timezone.utc)}
                )
            from database.sync_ledger import complete_batch_projection_in_transaction

            complete_batch_projection_in_transaction(
                transaction,
                session.ledger_ref,
                session.ledger,
                binding.job_id,
                result,
                datetime.fromtimestamp(now, timezone.utc),
                run_token=binding.run_token,
                run_epoch=binding.run_epoch,
            )
            for sibling in live_siblings:
                transaction.update(self.ref('jobs', sibling), {'client_status': 'completed', 'client_result': result})
            return result

        return self.run(commit)


class ProjectionSession:
    def __init__(self, store: ProjectionStore, segment_id: str, binding: ProjectionBinding, now: float):
        self.store, self.segment_id, self.binding, self.now = store, segment_id, binding, now
        self.client = store.client
        self.result_ref = store.ref('results', segment_id)
        self.owner_ref = store.ref('owners', owner_key(binding.owner_id))
        self.ledger_ref = sync_content_ledger_ref(self.client, binding.owner_id, binding.content_id)
        self.entry: dict[str, Any] = {}
        self.ledger: dict[str, Any] = {}
        self.job: dict[str, Any] = {}
        self.incoming_segment_count = 0
        self.speech_seconds = 0.0
        self.erased_predecessors: list[Any] = []

    def guard(self, transaction, conversation_ids=()):
        return assert_batch_write_allowed(
            self.client,
            transaction,
            self.binding.owner_id,
            conversation_ids=conversation_ids,
            expected_generation=self.binding.privacy_generation,
        )

    def prepare(self, transaction, *, replay=True):
        self.job = self.store.ref('jobs', self.segment_id).get(transaction=transaction).to_dict() or {}
        self.entry = self.result_ref.get(transaction=transaction).to_dict() or {}
        owner = self.owner_ref.get(transaction=transaction).to_dict() or {}
        self.ledger = self.ledger_ref.get(transaction=transaction).to_dict() or {}
        if (
            not self.job.get('projection_binding')
            or normalized_binding(self.job['projection_binding']) != self.binding
            or self.segment_id not in self.binding.segment_ids
            or self.job.get('owner_id') != self.binding.owner_id
            or self.entry.get('owner_key') != owner_key(self.binding.owner_id)
            or self.entry.get('protocol_version') != 1
            or self.entry.get('segment_id') != self.segment_id
            or self.entry.get('capture_at') != self.job.get('capture_at')
            or self.job.get('privacy_generation') != self.binding.privacy_generation
            or self.job.get('result') != self.entry.get('result')
            or 'previous_segment_id' not in self.entry
        ):
            raise ProjectionBlocked('immutable result binding mismatch')
        ids = [
            chunk_identity(
                self.binding.owner_id,
                self.binding.source,
                self.binding.client_device_id,
                self.binding.is_locked,
                self.job['capture_at'],
            )
        ]
        if self.binding.target_conversation_id:
            ids.append(self.binding.target_conversation_id)
        if self.job.get('conversation_id'):
            ids.append(self.job['conversation_id'])
        self.guard(transaction, ids)
        durable = self.ledger.get('batch_pipeline') or {}
        if (
            self.ledger.get('dispatch_protocol') != 'batch_v1'
            or durable
            != {
                'protocol_version': 1,
                'namespace': self.store.store.namespace,
                'segment_ids': list(self.binding.segment_ids),
            }
            or self.ledger.get('job_id') != self.binding.job_id
        ):
            raise ProjectionBlocked('durable intake ledger binding required')
        receipt = self.entry.get('projection')
        if not (receipt and self.ledger.get('status') == 'completed') and not batch_projection_ledger_owner_matches(
            self.ledger,
            self.binding.job_id,
            self.binding.run_token,
            self.binding.run_epoch,
        ):
            raise ProjectionBlocked('content ledger owner lost')
        if receipt:
            if replay:
                raise ProjectionReplay(receipt)
            return
        from database.batch_pipeline_privacy import erased_predecessors

        erased = erased_predecessors(
            self.client,
            transaction,
            self.store.store.namespace,
            owner_key(self.binding.owner_id),
            self.entry['previous_segment_id'],
            owner.get('projection_watermark'),
        )
        if erased is None:
            raise ProjectionBlocked('earlier committed projection must persist first')
        self.erased_predecessors = erased

    def validate_plan(self, transaction, planned):
        # encode is still in assignment's read-only planning phase.
        self.guard(transaction, [planned['id'], *(planned.get('sync_merged_from') or [])])

    def persist(self, transaction, planned=None):
        assigned, created, survivors = planned if planned is not None else ({}, False, [])
        repeat_only = assigned.get('_sync_lineage_repeat_only', False)
        receipt = {
            'state': 'persisted',
            'conversation_id': assigned.get('id'),
            'created': created,
            'language': assigned.get('language') or self.binding.language or 'en',
            'persisted_at': self.now,
            'audio_required': bool(survivors and self.binding.private_cloud_sync_enabled),
            'incoming_segment_count': self.incoming_segment_count,
            'speech_seconds': self.speech_seconds,
            'enrichment_required': bool(
                assigned.get('id') and (not repeat_only or assigned.get('_sync_lineage_completion_pending'))
            ),
        }
        transaction.update(self.result_ref, {'projection': receipt, 'projection_state': 'persisted'})
        transaction.update(self.owner_ref, {'projection_watermark': self.segment_id})
        for reference in self.erased_predecessors:
            transaction.update(
                reference,
                {
                    'expires_at': datetime.fromtimestamp(self.now, timezone.utc)
                    + timedelta(days=LEDGER_RETENTION_DAYS),
                },
            )
        # A read-before-write ledger checkpoint shares the assignment commit.
        transaction.update(
            self.ledger_ref,
            {
                'processed_segment_ids': firestore.ArrayUnion([self.segment_id]),
                'updated_at': datetime.fromtimestamp(self.now, timezone.utc),
            },
        )
        return receipt

    def persist_empty(self):
        @firestore.transactional
        def commit(transaction):
            self.prepare(transaction)
            return self.persist(transaction)

        return self.store.run(commit)
