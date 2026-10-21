"""Result-log projection receipts sharing the legacy assignment transaction.

No transcript bodies are copied into scheduler metadata. Durable completion is
separate from the Redis client projection, and can repair a lost Redis reply.
"""

from datetime import datetime, timezone
import logging
from typing import Any

from google.cloud import firestore

from database.batch_pipeline_policy import load_stage_policy
from config.policy import ProjectionPolicy
from database.fsr_read_cache import writing
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.sync_ledger import (
    BATCH_PARTIAL_STATUS,
    batch_projection_ledger_owner_matches,
    complete_batch_partial_in_transaction,
    sync_content_ledger_ref,
    is_valid_completed_sync_content_result,
)
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import owner_key
from database.batch_pipeline_projection_protocol import (
    ProjectionBlocked as ProjectionBlocked,
    ProjectionReplay as ProjectionReplay,
    normalized_binding,
)
from database.batch_pipeline_projection_session import ProjectionSession as ProjectionSession

logger = logging.getLogger(__name__)


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
        if job.get('projection_binding') and (job.get('policy_parts') or {}).get('projection') is None:
            job, _ = load_stage_policy(self.store, segment_id, 'projection')
        entry = self.ref('results', segment_id).get().to_dict() or {}
        if not entry or not job.get('projection_binding'):
            raise ProjectionBlocked('committed result and durable intake binding required')
        return job, entry, normalized_binding(job['projection_binding'])

    def projection_watermark(self, hashed_owner: str) -> str | None:
        # A fetch hint only; assignment rereads the watermark transactionally.
        return (self.ref('owners', hashed_owner).get().to_dict() or {}).get('projection_watermark')

    def policy(self, segment_id: str) -> ProjectionPolicy:
        _, policy = load_stage_policy(self.store, segment_id, 'projection')
        if policy is None:
            raise ProjectionBlocked('durable projection policy required')
        return policy

    def session(self, segment_id: str, binding: ProjectionBinding, now: float, **part):
        return ProjectionSession(self, segment_id, binding, now, **part)

    def ready(self, segment_id: str, binding: ProjectionBinding, now: float, *, part_index=None, policy=None) -> dict:
        """Acknowledge a replayable post-persist mark; never append again."""

        policy = policy or self.policy(segment_id)

        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now, part_index=part_index, policy=policy)
            session.prepare(transaction, replay=False)
            receipt = dict(session.receipt())
            if not receipt:
                raise ProjectionBlocked('projection must persist before enrichment acknowledgment')
            receipt['state'] = 'ready'
            session.write_receipt(transaction, receipt)
            return receipt

        return self.run(commit, policy=policy)

    def check(self, session):
        @firestore.transactional
        def read(transaction):
            session.prepare(transaction)

        self.run(read, policy=session.policy)

    def acknowledge(self, segment_id: str, binding: ProjectionBinding, now: float, *, policy=None):

        policy = policy or self.policy(segment_id)

        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now, policy=policy)
            session.prepare(transaction, replay=False)
            if session.ledger.get('status') != 'completed':
                raise ProjectionBlocked('client publication preceded durable completion')
            transaction.update(session.result_ref, {'projection_state': 'completed'})

        self.run(commit, policy=policy)

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

    def mark_enrichment(
        self,
        segment_id: str,
        binding: ProjectionBinding,
        now: float,
        canonical: str,
        language: str,
        *,
        part_index=None,
        policy=None,
    ):
        from utils.sync import reprocess

        policy = policy or self.policy(segment_id)

        def mutate(document_id, operation):
            @firestore.transactional
            def commit(transaction):
                session = self.session(segment_id, binding, now, part_index=part_index, policy=policy)
                session.prepare(transaction, replay=False)
                session.guard(transaction, [canonical])
                receipt = dict(session.receipt())
                ref = self.client.collection(reprocess.COLLECTION).document(document_id)
                snapshot = ref.get(transaction=transaction)
                old = snapshot.to_dict() if snapshot.exists else None
                if receipt.get('state') == 'ready':
                    return {**(old or {}), '_wake': False}, True
                row, result = operation(old)
                if old is None and session.job.get('priority') != 0:
                    from utils.cloud_tasks import is_sync_backfill_routing_enabled

                    if is_sync_backfill_routing_enabled():
                        import os

                        queue = os.getenv('SYNC_BACKFILL_TASKS_QUEUE', '').strip()
                        handler = os.getenv('SYNC_BACKFILL_TASKS_HANDLER_URL', '').strip()
                        if not queue or not handler:
                            raise ProjectionBlocked('backfill enrichment dispatch binding required')
                        dispatch = {
                            'queue': queue,
                            'handler': handler,
                            'audience': os.getenv('SYNC_BACKFILL_TASKS_OIDC_AUDIENCE') or handler,
                            'invoker_sa': os.getenv('SYNC_TASKS_INVOKER_SA', ''),
                        }
                        if not reprocess.valid_dispatch_binding(dispatch):
                            raise ProjectionBlocked('complete backfill enrichment dispatch binding required')
                        row['dispatch'] = dispatch
                        result = (row, result[1])
                # The enrichment obligation and its exactly-once projection
                # receipt commit together, fenced against account deletion.
                transaction.set(ref, row)
                receipt.update(state='ready', conversation_id=canonical)
                session.write_receipt(transaction, receipt)
                return result

            return self.run(commit, policy=policy)

        reprocess.mark(binding.owner_id, canonical, language, now=now, mutate=mutate, snapshot_summary=True)

    def run(self, operation, *, policy=None):
        # Same bounded opt-in read-contention retry as legacy sync (#21680).
        import os
        from database._client import run_transactional
        from database.firestore_transaction_retry import run_with_transaction_contention_retry

        if (
            not (policy and policy.projection_contention)
            and os.getenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'false').strip().lower() != 'true'
        ):
            return run_transactional(self.client, operation)
        return run_with_transaction_contention_retry(
            self.client.transaction,
            lambda transaction: run_transactional(self.client, operation, initial_transaction=transaction),
            operation_name='batch_projection',
        )

    def hold_for_quarantine(self, segment_id: str, binding: ProjectionBinding, now: float, *, policy=None) -> bool:
        """Stop re-sweeping a persisted sibling; keep ledger/assignment fences intact."""

        policy = policy or self.policy(segment_id)

        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now, policy=policy)
            session.prepare(transaction, replay=False)
            if session.receipt().get('state') != 'ready':
                return False
            held = False
            for sibling in binding.segment_ids:
                job = self.ref('jobs', sibling).get(transaction=transaction).to_dict() or {}
                if job.get('state') == 'quarantined':
                    if (
                        not job.get('projection_binding')
                        or normalized_binding(job['projection_binding']) != binding
                        or job.get('merge_pending') is not False
                    ):
                        raise ProjectionBlocked('quarantined sibling binding mismatch')
                    held = True
            if held:
                transaction.update(session.result_ref, {'projection_state': 'quarantine_held'})
            return held

        return self.run(commit, policy=policy)

    def prepare_accounting(self, binding: ProjectionBinding, now: float, *, held: bool = False) -> dict | None:
        """Resolve usage attribution outside the retryable completion transaction.

        ``held`` accounts a partial: quarantined siblings without a receipt are
        skipped (their eligibility is rechecked in the partial transaction). A
        partial ledger already charged its projected speech, so only the
        difference is charged again.
        """
        import math

        seconds = 0.0
        source = 'sync_backfill'
        for sid in binding.segment_ids:
            entry = self.ref('results', sid).get().to_dict() or {}
            if entry.get('projection_state') == 'erased':
                continue
            receipt = entry.get('projection') or {}
            if receipt.get('state') != 'ready':
                # Only a unit nothing automatic will change; an open intent or a
                # recoverable unit means this upload is not a partial yet.
                if held and not entry and held_without_recovery(self.ref('jobs', sid).get().to_dict() or {}):
                    continue
                return None
            value = receipt.get('speech_seconds')
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ProjectionBlocked('validated speech accounting receipt required')
            seconds += value
            job = self.ref('jobs', sid).get().to_dict() or {}
            if job.get('priority') == 0:
                source = 'sync_fresh'
        ledger = sync_content_ledger_ref(self.client, binding.owner_id, binding.content_id).get().to_dict() or {}
        if held and not batch_projection_ledger_owner_matches(
            ledger, binding.job_id, binding.run_token, binding.run_epoch
        ):
            # Charge nothing for a partial that cannot commit.
            return None
        charged = ledger.get('usage_committed_seconds', 0.0) if ledger.get('status') == BATCH_PARTIAL_STATUS else 0.0
        steps, step_times = charge_chain(ledger) if ledger.get('status') == BATCH_PARTIAL_STATUS else ([0.0], [])
        if binding.native_record:
            return {
                'seconds': seconds,
                'source': 'realtime',
                'updates': {},
                'hour': '',
                'completed': True,
                'charged': charged,
                'steps': steps,
                'step_times': step_times,
            }
        stamp = datetime.fromtimestamp(now, timezone.utc)
        updates = {}
        if int(seconds) - int(charged) > 0 and ledger.get('status') != 'completed':
            from database.llm_usage import resolve_usage_plan_id
            from database.hourly_usage_updates import prepare_hourly_usage_updates

            delta = int(seconds) - int(charged)
            updates = prepare_hourly_usage_updates(
                stamp,
                {'transcription_seconds': delta, 'speech_seconds': delta},
                resolve_usage_plan_id(binding.owner_id, firestore_client=self.client),
                usage_metadata={'funding': 'omi', 'provider': 'parakeet', 'source': 'sync_v2'},
            )
        return {
            'seconds': seconds,
            'source': source,
            'updates': updates,
            'hour': f'{stamp.year}-{stamp.month:02d}-{stamp.day:02d}-{stamp.hour:02d}',
            'completed': ledger.get('status') == 'completed',
            'charged': charged,
            'steps': steps,
            'step_times': step_times,
        }

    def complete(
        self, segment_id: str, binding: ProjectionBinding, now: float, accounting: dict, *, policy=None
    ) -> dict | None:
        """Complete only after every bound sibling persisted and marked enrichment."""
        policy = policy or self.policy(segment_id)

        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now, policy=policy)
            session.prepare(transaction, replay=False)
            receipts = []
            live_siblings = []
            erased_count = 0
            captured_seconds = 0.0
            terminal_empty_count = 0
            for sibling in binding.segment_ids:
                job = self.ref('jobs', sibling).get(transaction=transaction).to_dict() or {}
                entry = self.ref('results', sibling).get(transaction=transaction).to_dict() or {}
                if entry.get('projection_state') == 'erased':
                    if entry.get('owner_key') != owner_key(binding.owner_id) or entry.get('segment_id') != sibling:
                        raise ProjectionBlocked('erased sibling owner mismatch')
                    receipts.append({'state': 'ready', 'conversation_id': None, 'created': False})
                    erased_count += 1
                    continue
                if entry.get('result', {}).get('outcome') == 'no_recoverable_speech':
                    terminal_empty_count += 1
                live_siblings.append(sibling)
                captured_seconds += job.get('duration_seconds', 0.0)
                if not job.get('projection_binding') or normalized_binding(job['projection_binding']) != binding:
                    raise ProjectionBlocked('sibling binding mismatch')
                receipt = entry.get('projection') or {}
                if receipt.get('state') != 'ready':
                    return None, False, 0
                parts = entry.get('projection_parts')
                receipts.extend(parts.values() if parts else [receipt])
            new, updated = self._visible(transaction, binding, receipts)
            superseded_count = sum(receipt.get('disposition') == 'superseded' for receipt in receipts)
            # Re-read canonical deletion fences before publishing any visible IDs.
            session.guard(transaction, (*new, *updated))
            result = {
                'new_memories': new,
                'updated_memories': updated,
                'failed_segments': 0,
                'total_segments': len(receipts),
                'errors': [],
                'outcome': (
                    'success'
                    if new or updated or erased_count or terminal_empty_count or superseded_count
                    else 'expected_silence'
                ),
            }
            if terminal_empty_count:
                result['no_recoverable_speech_segments'] = terminal_empty_count
            if superseded_count:
                result['superseded_segments'] = superseded_count
            if session.ledger.get('status') == 'completed':
                old = session.ledger.get('result')
                if not is_valid_completed_sync_content_result(old):
                    raise ProjectionBlocked('invalid existing ledger completion')
                return old, False, 0
            # Part-level attribution need not sum to the worker's speech union
            # for older receipts. The immutable result summary owns metering.
            seconds = sum(
                (self.ref('results', sid).get(transaction=transaction).to_dict() or {})
                .get('projection', {})
                .get('speech_seconds', 0.0)
                for sid in live_siblings
            )
            if seconds != accounting['seconds']:
                raise ProjectionBlocked('speech accounting changed during completion')
            self._commit_usage(transaction, session.ledger_ref, session.ledger, binding, accounting, seconds, now)
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
                # All assignment/enrichment receipts now exist. Wake held
                # siblings in the same durable completion, including a crash
                # before client publication or completion retention.
                transaction.update(self.ref('results', sibling), {'projection_state': 'ready'})
                transaction.update(self.ref('jobs', sibling), {'client_status': 'completed', 'client_result': result})
            return result, True, captured_seconds

        with writing('usage_month_cache', binding.owner_id):
            result, changed, seconds = self.run(commit, policy=policy)
        if changed:
            record_correctness('projection_completed', seconds=seconds)
        return result

    def _visible(self, transaction, binding: ProjectionBinding, receipts) -> tuple[list[str], list[str]]:
        """Earlier receipt IDs can have become bridge donors. Follow the same
        server redirects, retaining only visible canonical IDs."""
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
        return new, updated

    def _commit_usage(self, transaction, ledger_ref, ledger, binding, accounting, seconds, now) -> None:
        """Charge projected speech once; a partial's later completion charges only the rest."""
        partial = ledger.get('status') == BATCH_PARTIAL_STATUS
        charged = ledger.get('usage_committed_seconds', 0.0) if partial else 0.0
        if charged != accounting.get('charged', 0.0):
            raise ProjectionBlocked('usage accounting changed during completion')
        if ledger.get('usage_committed_at') is not None and not partial:
            return
        if accounting['updates']:
            usage_ref = (
                self.client.collection('users')
                .document(binding.owner_id)
                .collection('hourly_usage')
                .document(accounting['hour'])
            )
            transaction.set(usage_ref, accounting['updates'], merge=True)
        # Every charge boundary and when it committed, so fair use can re-issue
        # each recent step's once-key: a write lost after any earlier commit
        # still lands on a later attempt while that key is live.
        steps, times = extend_chain(*(charge_chain(ledger) if partial else ([0.0], [])), seconds, now)
        transaction.update(
            ledger_ref,
            {
                'usage_committed_at': datetime.fromtimestamp(now, timezone.utc),
                'usage_committed_seconds': seconds,
                'usage_steps': steps,
                'usage_step_times': times,
            },
        )

    def complete_partial(
        self, binding: ProjectionBinding, now: float, accounting: dict
    ) -> tuple[dict, list[float]] | None:
        """Terminal partial once every unprojected unit is held with no recovery path left.

        Projected siblings are published under the completion's redirect and
        privacy fences; held units keep their state, intents and retained audio,
        so a reviewed redrive can still recover them and the ordinary completion
        then upgrades the row. Usage covers projected speech only. Returns the
        result and the durable charge step (previous, committed seconds), the
        same on a replay, or None while any sibling can still change or nothing
        is held.
        """

        @firestore.transactional
        def commit(transaction):
            ledger_ref = sync_content_ledger_ref(self.client, binding.owner_id, binding.content_id)
            ledger = ledger_ref.get(transaction=transaction).to_dict() or {}
            if ledger.get('status') == 'completed':
                return None, False
            if (
                ledger.get('dispatch_protocol') != 'batch_v1'
                or ledger.get('batch_pipeline')
                != {
                    'protocol_version': 1,
                    'namespace': self.store.namespace,
                    'segment_ids': list(binding.segment_ids),
                }
                or not batch_projection_ledger_owner_matches(
                    ledger, binding.job_id, binding.run_token, binding.run_epoch
                )
            ):
                raise ProjectionBlocked('content ledger owner lost')
            receipts, seconds, held = [], 0.0, 0
            erased_count = terminal_empty_count = 0
            for sibling in binding.segment_ids:
                job = self.ref('jobs', sibling).get(transaction=transaction).to_dict() or {}
                entry = self.ref('results', sibling).get(transaction=transaction).to_dict() or {}
                if entry.get('projection_state') == 'erased':
                    if entry.get('owner_key') != owner_key(binding.owner_id) or entry.get('segment_id') != sibling:
                        raise ProjectionBlocked('erased sibling owner mismatch')
                    receipts.append({'state': 'ready', 'conversation_id': None, 'created': False})
                    erased_count += 1
                    continue
                if not job.get('projection_binding') or normalized_binding(job['projection_binding']) != binding:
                    raise ProjectionBlocked('sibling binding mismatch')
                if not entry and held_without_recovery(job):
                    held += 1
                    continue
                receipt = entry.get('projection') or {}
                if receipt.get('state') != 'ready':
                    return None, False
                if entry.get('result', {}).get('outcome') == 'no_recoverable_speech':
                    terminal_empty_count += 1
                seconds += receipt.get('speech_seconds', 0.0)
                parts = entry.get('projection_parts')
                receipts.extend(parts.values() if parts else [receipt])
            if not held:
                return None, False
            new, updated = self._visible(transaction, binding, receipts)
            # Re-read canonical deletion fences before publishing any visible IDs.
            assert_batch_write_allowed(
                self.client,
                transaction,
                binding.owner_id,
                conversation_ids=(*new, *updated),
                expected_generation=binding.privacy_generation,
            )
            result = {
                'new_memories': new,
                'updated_memories': updated,
                'failed_segments': held,
                'held_segments': held,
                'total_segments': len(receipts) + held,
                'errors': [],
                'outcome': 'partial',
            }
            if terminal_empty_count:
                result['no_recoverable_speech_segments'] = terminal_empty_count
            superseded_count = sum(receipt.get('disposition') == 'superseded' for receipt in receipts)
            if superseded_count:
                result['superseded_segments'] = superseded_count
            if ledger.get('status') == BATCH_PARTIAL_STATUS and ledger.get('result') == result:
                return (result, charge_chain(ledger)), False
            if seconds != accounting['seconds']:
                raise ProjectionBlocked('speech accounting changed during completion')
            chain = charge_chain(ledger) if ledger.get('status') == BATCH_PARTIAL_STATUS else ([0.0], [])
            self._commit_usage(transaction, ledger_ref, ledger, binding, accounting, seconds, now)
            complete_batch_partial_in_transaction(
                transaction,
                ledger_ref,
                ledger,
                binding.job_id,
                result,
                datetime.fromtimestamp(now, timezone.utc),
                run_token=binding.run_token,
                run_epoch=binding.run_epoch,
            )
            return (result, extend_chain(*chain, seconds, now)), True

        with writing('usage_month_cache', binding.owner_id):
            outcome, changed = self.run(commit)
        if changed:
            logger.info('event=batch_held_partial outcome=completed held=%d', outcome[0]['held_segments'])
        return outcome


def charge_chain(ledger: dict) -> tuple[list[float], list[float | None]]:
    """A partial ledger's charge boundaries (from 0.0) and each step's commit time.

    A step without a recorded time (an unknown age) is never re-issued: its
    fair-use once-key may already have expired.
    """
    steps = ledger.get('usage_steps')
    if not (isinstance(steps, list) and steps and steps[0] == 0.0):
        committed = ledger.get('usage_committed_seconds', 0.0)
        steps = [0.0, committed] if committed else [0.0]
    times = ledger.get('usage_step_times')
    if not (isinstance(times, list) and len(times) == len(steps) - 1):
        times = [None] * (len(steps) - 1)
    return list(steps), list(times)


def extend_chain(steps, times, seconds: float, now: float) -> tuple[list[float], list[float | None]]:
    if seconds > steps[-1]:
        return [*steps, seconds], [*times, now]
    return list(steps), list(times)


# A reviewed operator intent that is not settled can still change its unit.
OPERATOR_INTENTS = ('speech_redrive', 'terminal_disposition', 'silence_disposition')


def held_without_recovery(job: dict) -> bool:
    """A quarantined unit that nothing automatic will change.

    Its one paid recovery settled without words (``failed_held``), or its
    recorded recovery policy is off and no paid call was ever authorized. Either
    way its encrypted audio stays server-side for a reviewed operator redrive.
    """
    from config.policy import RecoveryPolicy

    if job.get('state') != 'quarantined' or job.get('result'):
        return False
    if any(
        isinstance(job.get(key), dict) and job[key].get('state') not in {'completed', 'failed_held'}
        for key in OPERATOR_INTENTS
    ):
        return False
    if job.get('recovery_state') == 'failed_held':
        return True
    raw = (job.get('policy_parts') or {}).get('recovery')
    return (
        job.get('recovery_state') == 'held'
        and not job.get('recovery')
        and isinstance(raw, dict)
        and not RecoveryPolicy.from_dict(raw).recovery_enabled
    )
