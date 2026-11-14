"""Result-log projection receipts sharing the legacy assignment transaction.

No transcript bodies are copied into scheduler metadata. Durable completion is
separate from the Redis client projection, and can repair a lost Redis reply.
"""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

from google.cloud import firestore

from config.batch_pipeline import projection_followup_page_enabled, projection_source_deleted_enabled
from database.batch_pipeline_policy import load_stage_policy
from database.batch_pipeline_delivered_share import delivery_stamp
from database.batch_pipeline_shadow_hook import mirror_refresh
from config.policy import ProjectionPolicy
from database.fsr_read_cache import writing
from database.monthly_usage_totals import queue_increment
from database.batch_pipeline_store import FirestoreStore
from database import batch_pipeline_coalescing_completion as coalescing_completion
from database.batch_pipeline_projection_finish import (
    PROJECTION_FINISH_DUE_FIELD,
    PROJECTION_FINISH_STATES,
    PROJECTION_FINISH_STEP_FIELD,
    projection_finish_state_fields,
)
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyBlocked, BatchPrivacyReason
from database.batch_pipeline_projection_privacy import HOLD_REASONS
from database.batch_pipeline_artifact_missing import artifact_missing, REASON_CODE as ARTIFACT_MISSING_REASON
from database.sync_ledger_ownership import batch_projection_ledger_owner_matches
from database.sync_ledger import (
    BATCH_PARTIAL_STATUS,
    complete_batch_partial_in_transaction,
    sync_content_ledger_ref,
    is_valid_completed_sync_content_result,
)
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.projection_hold_observability import log_projection_hold
from utils.batch_pipeline.scheduler import owner_key
from database.batch_pipeline_projection_protocol import (
    ProjectionBlocked as ProjectionBlocked,
    ProjectionReplay as ProjectionReplay,
    normalized_binding,
)
from database.batch_pipeline_projection_session import ProjectionSession as ProjectionSession, SOURCE_DELETED_JOBS

logger = logging.getLogger(__name__)

_USAGE_PERIOD = re.compile(r'(\d{4})-(\d{2})')


def usage_stamp(now: datetime, usage_period: Any) -> datetime:
    """Hour stamp for projection usage: ``now``, backdated into ``usage_period`` only across a rollover.

    A cap-hold unit admitted under the owner's funded choice in month M is billed to M even when
    projection completes in M+1 (lane 6, Subscription ruling B(a)). The stamp moves only backwards, to
    the period's last second, and the hourly doc id/year/month/day/hour all derive from it, so the
    month query reads it as M (transcription has no day rollup). Missing or malformed periods keep now.
    """
    match = _USAGE_PERIOD.fullmatch(usage_period) if isinstance(usage_period, str) else None
    if match is None or not 1 <= int(match.group(2)) <= 12:
        return now
    start = datetime(int(match.group(1)), int(match.group(2)), 1, tzinfo=timezone.utc)
    end = (start + timedelta(days=32)).replace(day=1)
    return end - timedelta(seconds=1) if now >= end else now


class ProjectionStore:
    def __init__(self, store: FirestoreStore):
        self.store = store

    @property
    def client(self):
        return self.store.client

    def ref(self, table: str, key: str):
        return self.client.collection(f'{self.store.namespace}_{table}').document(key)

    def _mirror(self, binding: ProjectionBinding, extra: list[tuple[str, str]] | tuple = ()) -> None:
        # A2 shadow: these transactions write batch docs outside Store.run; no-op unless shadow mode.
        # The owner row too: assignment advances its projection_watermark (staging 10-20: 59 owners rows
        # diverged at rest because no refresh named them).
        namespace = getattr(self.store, 'namespace', '')
        keys = [(t, s) for s in binding.segment_ids for t in ('jobs', 'results')]
        mirror_refresh(namespace, [*keys, ('owners', owner_key(binding.owner_id)), *extra])

    def mirror_assignment(self, session: Any) -> None:
        """After an assignment transaction (``assign_sync_conversation``): re-copy the binding's rows, the
        owner's watermark and the erased predecessors whose ``expires_at`` it stamped. Never raises."""
        try:
            erased = [('results', reference.id) for reference in getattr(session, 'erased_predecessors', ())]
            self._mirror(session.binding, erased)
        except Exception:
            logger.warning('event=jobstore_shadow op=refresh outcome=hook_error site=projection_assignment')

    def _settle_allowance(self, binding: ProjectionBinding, now: float, accounting: dict, segment_ids) -> None:
        """Post-billing shadow settlement; replay repairs a lost observer reply."""
        if accounting.get('source_deleted'):
            return
        try:
            from utils.stt.allowance_batch import observe_billed_batch

            if not isinstance(accounting.get('updates'), dict) or 'seconds' not in accounting:
                return
            observe_billed_batch(
                self.client,
                binding.owner_id,
                binding.content_id,
                accounting.get('billing_generation'),
                segment_ids,
                now,
            )
        except Exception:
            logger.warning('event=free_allowance_lease decision=settlement_unavailable')

    def _observe_transcription(self, binding: ProjectionBinding, now: float, accounting: dict, result: dict) -> None:
        """Fail-open C1 transcript-landed write: ``sealed -> transcribed``.

        Runs after the durable completion that published this capture's
        transcript, on the same event clock (``now``) the completion used. Only a
        first completion reaches here: a replay returns an earlier result with
        no write, and a source deletion keeps its erasure fence and gets no new
        durable row. Speech counters come from the immutable completion summary,
        never from a query.
        """
        capture_id = binding.target_conversation_id
        if not isinstance(capture_id, str) or not capture_id:
            return
        if accounting.get('source_deleted') or (result or {}).get('reason_code') == 'source_deleted':
            return
        seconds = accounting.get('seconds')
        speech_seconds = float(seconds) if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else 0.0
        try:
            from database import pipeline_ledger

            pipeline_ledger.advance(
                binding.owner_id,
                capture_id,
                pipeline_ledger.TRANSCRIBED,
                now=now,
                speech_seconds=speech_seconds,
                has_speech=speech_seconds > 0,
                speech_basis='transcript',
                firestore_client=self.client,
            )
        except Exception as error:  # The durable completion is already authoritative.
            logger.warning(
                'event=batch_projection action=ledger outcome=error stage=transcribed exception_type=%s',
                type(error).__name__,
            )

    def read(self, segment_id: str) -> tuple[dict[str, Any], dict[str, Any], ProjectionBinding]:
        # This snapshot is a fetch hint only. Every mutation rereads it atomically.
        job: dict[str, Any] = self.ref('jobs', segment_id).get().to_dict() or {}
        if job.get('projection_binding') and (job.get('policy_parts') or {}).get('projection') is None:
            try:
                job, _ = load_stage_policy(self.store, segment_id, 'projection')
            except BatchPrivacyBlocked as error:
                if error.reason != BatchPrivacyReason.CONVERSATION_DELETED and error.reason not in HOLD_REASONS:
                    raise
                # Deletion may win before the projection policy was first
                # pinned. No policy or source mutation is allowed then. These
                # local code defaults only drive no-text settlement/replay;
                # Projector must never assign a job carrying this hint.
                job = {
                    **job,
                    **(
                        {'_projection_privacy_deleted': True}
                        if error.reason == BatchPrivacyReason.CONVERSATION_DELETED
                        else {'_projection_privacy_refusal': error.reason.value}
                    ),
                    'policy_parts': {**(job.get('policy_parts') or {}), 'projection': ProjectionPolicy().to_dict()},
                }
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
            sibling_held = session.write_receipt(transaction, receipt)
            return receipt, sibling_held

        receipt, sibling_held = self.run(commit, policy=policy)
        if sibling_held:
            log_projection_hold('sibling')
        self._mirror(binding)
        return receipt

    def check(self, session):
        @firestore.transactional
        def read(transaction):
            session.prepare(transaction)

        self.run(read, policy=session.policy)

    def settle_deleted_output(self, segment_id, binding, now, receipt, *, part_index=None, policy=None):
        """Retire only an already-assigned output, preserving all input speech accounting."""
        output = receipt.get('conversation_id')
        if not output:
            return
        user = self.client.collection('users').document(binding.owner_id)
        candidate = output
        seen = set()
        # Cheap read hint; the mutation below rechecks the complete fence in
        # its transaction. Follow server redirects exactly as the privacy guard.
        while candidate and candidate not in seen and len(seen) < 256:
            seen.add(candidate)
            if user.collection('deleted_conversations').document(candidate).get().exists:
                break
            row = user.collection('conversations').document(candidate).get().to_dict() or {}
            candidate = row.get('sync_merged_into') if row.get('deleted') else None
        else:
            return
        if not candidate or not user.collection('deleted_conversations').document(candidate).get().exists:
            return
        policy = policy or self.policy(segment_id)

        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now, part_index=part_index, policy=policy)
            session.prepare(transaction, replay=False)
            current = session.receipt()
            if current.get('conversation_id') != output:
                return current, False
            try:
                session.guard(transaction, [output])
            except BatchPrivacyBlocked as error:
                if error.reason != BatchPrivacyReason.CONVERSATION_DELETED or not error.conversation_id:
                    raise
                if (
                    not user.collection('deleted_conversations')
                    .document(error.conversation_id)
                    .get(transaction=transaction)
                    .exists
                ):
                    raise
            else:
                return current, False
            settled = {
                **current,
                'state': 'ready',
                'conversation_id': None,
                'audio_required': False,
                'enrichment_required': False,
                'disposition': 'output_deleted',
            }
            sibling_held = session.write_receipt(transaction, settled)
            return settled, sibling_held

        settled, sibling_held = self.run(commit, policy=policy)
        if sibling_held:
            log_projection_hold('sibling')
        receipt.update(settled)
        self._mirror(binding)

    def defer_finish(self, segment_id: str, state: str | None, now: float) -> bool:
        """Bound when the finish page retries a row whose last walk changed nothing.

        The fence re-reads ``projection_state`` inside the transaction. A row
        that moved on is left untouched: its own state write already stamped it
        due now, so a stale write can never defer a row with new work. Repeats
        escalate 60 s, 300 s, 900 s and stay capped; only the lever's sweep
        calls this, and a lever-off caller writes nothing. ``state`` is ``None``
        when the sweep could not read the row: the clock is then stamped only
        while the row is still in a finish state, so a failed read cannot strand
        it and cannot touch a completed or pending row.
        """
        from config.batch_pipeline import PROJECTION_FINISH_BACKOFF_SECONDS, projection_finish_backoff_delay

        @firestore.transactional
        def commit(transaction):
            ref = self.ref('results', segment_id)
            row = ref.get(transaction=transaction).to_dict() or {}
            current = row.get('projection_state')
            if state is not None and current != state:
                return False
            if current not in PROJECTION_FINISH_STATES:
                return False
            previous = row.get(PROJECTION_FINISH_STEP_FIELD)
            cap = len(PROJECTION_FINISH_BACKOFF_SECONDS) - 1
            step = min(previous + 1, cap) if isinstance(previous, int) and previous >= 0 else 0
            transaction.update(
                ref,
                {
                    PROJECTION_FINISH_DUE_FIELD: now + projection_finish_backoff_delay(step),
                    PROJECTION_FINISH_STEP_FIELD: step,
                },
            )
            return True

        return bool(self.run(commit))

    def acknowledge(self, segment_id: str, binding: ProjectionBinding, now: float, *, policy=None):

        policy = policy or self.policy(segment_id)

        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now, policy=policy)
            session.prepare(transaction, replay=False)
            if session.ledger.get('status') != 'completed':
                raise ProjectionBlocked('client publication preceded durable completion')
            delivered_at, delivered_in_target = delivery_stamp(session.job, now)
            transaction.update(
                session.result_ref,
                {
                    'projection_state': 'completed',
                    **projection_finish_state_fields('completed', now),
                },
            )
            # The delivered-share sampler reads jobs, not results: a unit whose
            # projection never completes still has an admission row there.
            transaction.update(
                session.job_ref,
                {'delivered_at': delivered_at, 'delivered_in_target': delivered_in_target},
            )

        self.run(commit, policy=policy)
        self._mirror(binding)

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
        from config.sync_reprocess import settle_seconds
        from database.outbox_firestore import FirestoreEnrichmentOutbox
        from utils.enrichment import outbox as reprocess

        if not reprocess.owns_runtime():
            raise RuntimeError('sync reprocess projection requires production or a Firestore emulator')
        policy = policy or self.policy(segment_id)
        outbox = FirestoreEnrichmentOutbox(self.client)

        def commit(transaction):
            session = self.session(segment_id, binding, now, part_index=part_index, policy=policy)
            session.prepare(transaction, replay=False)
            receipt = dict(session.receipt())
            output_ids = [r['conversation_id'] for r in receipt.get('size_rollover_outputs', [])] or [canonical]
            session.guard(transaction, output_ids)
            if receipt.get('state') == 'ready':
                return None
            backfill = session.job.get('priority') != 0
            # The enrichment obligation and its exactly-once projection
            # receipt commit together, fenced against account deletion.
            completed = receipt.get('size_rollover_enriched', [])
            output_id = next(cid for cid in output_ids if cid not in completed)
            result = outbox.enqueue(
                reprocess.key(binding.owner_id, output_id),
                binding.owner_id,
                {'conversation_id': output_id, 'language': language},
                now + settle_seconds(),
                tx=_ClientTransaction(self.client, transaction),
                now=now,
                new_dispatch=self._backfill_dispatch if backfill else None,
                snapshot_summary=True,
            )
            completed = [*completed, output_id]
            finished = len(completed) == len(output_ids)
            if len(output_ids) > 1:
                receipt['size_rollover_enriched'] = completed
            receipt.update(state='ready' if finished else 'persisted', conversation_id=canonical)
            sibling_held = session.write_receipt(transaction, receipt)
            return result, finished, sibling_held

        while True:
            committed = self.run(firestore.transactional(commit), policy=policy)
            if committed is None:
                break
            result, finished, sibling_held = committed
            if sibling_held:
                log_projection_hold('sibling')
            if result.wake_token:
                outbox.wake(result.row_id, result.wake_token)  # Durable before wake; the sweep repairs a miss.
            if finished:
                break
        self._mirror(binding)  # after the wake: the first-summary dispatch path never waits on the shadow

    @staticmethod
    def _backfill_dispatch() -> dict[str, str] | None:
        """A backfill unit keeps the backfill queue binding on a new obligation (None: host binding)."""
        from utils.cloud_tasks import is_sync_backfill_routing_enabled
        from utils.enrichment import outbox as reprocess

        if not is_sync_backfill_routing_enabled():
            return None
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
        return dispatch

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
            # attempts=1: the outer budget owns every attempt, so an expired
            # chain costs one bounded outer retry instead of inner restarts.
            lambda transaction: run_transactional(self.client, operation, initial_transaction=transaction, attempts=1),
            operation_name='batch_projection',
        )

    def hold_for_quarantine(self, segment_id: str, binding: ProjectionBinding, now: float, *, policy=None) -> bool:
        """Stop re-sweeping a persisted sibling; keep ledger/assignment fences intact."""

        policy = policy or self.policy(segment_id)
        group_ready = projection_followup_page_enabled()

        @firestore.transactional
        def commit(transaction):
            session = self.session(segment_id, binding, now, policy=policy)
            session.prepare(transaction, replay=False)
            if session.receipt().get('state') != 'ready':
                return False
            held = False
            ready = []
            for sibling in binding.segment_ids:
                job = self.ref('jobs', sibling).get(transaction=transaction).to_dict() or {}
                result = self.ref('results', sibling).get(transaction=transaction).to_dict() or {}
                if (result.get('projection') or {}).get('state') == 'quarantined':
                    if not job.get('projection_binding') or normalized_binding(job['projection_binding']) != binding:
                        raise ProjectionBlocked('quarantined sibling binding mismatch')
                    held = True
                if job.get('state') == 'quarantined':
                    if (
                        not job.get('projection_binding')
                        or normalized_binding(job['projection_binding']) != binding
                        or job.get('merge_pending') is not False
                    ):
                        raise ProjectionBlocked('quarantined sibling binding mismatch')
                    held = True
                if (
                    group_ready
                    and (result.get('projection') or {}).get('state') == 'ready'
                    and result.get('projection_state') in {'persisted', 'ready'}
                ):
                    if (
                        not job.get('projection_binding')
                        or normalized_binding(job['projection_binding']) != binding
                        or job.get('owner_id') != binding.owner_id
                        or result.get('owner_key') != owner_key(binding.owner_id)
                        or result.get('segment_id') != sibling
                    ):
                        raise ProjectionBlocked('ready sibling binding mismatch')
                    ready.append(self.ref('results', sibling))
            if held:
                # Ready receipts have completed their follow-ups even when a
                # sibling is held. Settle their hints without inventing holds.
                for ref in ready if group_ready else [session.result_ref]:
                    transaction.update(
                        ref, {'projection_state': 'ready', **projection_finish_state_fields('ready', now)}
                    )
            return held

        held = self.run(commit, policy=policy)
        self._mirror(binding)
        return held

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
        source_deleted = False
        for sid in binding.segment_ids:
            entry = self.ref('results', sid).get().to_dict() or {}
            if entry.get('projection_state') == 'erased':
                continue
            parts = entry.get('projection_parts')
            source_deleted = source_deleted or any(
                part.get('disposition') == 'source_deleted'
                for part in (parts.values() if parts else [entry.get('projection') or {}])
            )
            receipt = entry.get('projection') or {}
            if receipt.get('state') != 'ready':
                # Only a unit nothing automatic will change; an open intent or a
                # recoverable unit means this upload is not a partial yet.
                if held and not entry and held_without_recovery(self.ref('jobs', sid).get().to_dict() or {}):
                    continue
                if held and assignment_held_without_recovery(self.ref('jobs', sid).get().to_dict() or {}, entry):
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
        if source_deleted:
            if not projection_source_deleted_enabled():
                raise ProjectionBlocked('privacy disposition requires a source deletion tombstone')
            # Settled deletion receipts are immutable. Suppress pre-completion
            # fair-use dispatch and avoid resolving any new usage attribution.
            # Completion rechecks every part in its transaction before writing.
            return {
                'seconds': seconds,
                'source': source,
                'updates': {},
                'completed': ledger.get('status') == 'completed',
                'source_deleted': True,
            }
        charged = ledger.get('usage_committed_seconds', 0.0) if ledger.get('status') == BATCH_PARTIAL_STATUS else 0.0
        steps, step_times = charge_chain(ledger) if ledger.get('status') == BATCH_PARTIAL_STATUS else ([0.0], [])
        intake = self.ref('intakes', binding.job_id).get().to_dict() or {}
        if binding.native_record and intake.get('server_batch_only') is not True:
            return {
                'seconds': seconds,
                'source': 'realtime',
                'updates': {},
                'hour': '',
                'completed': True,
                'charged': charged,
                'steps': steps,
                'step_times': step_times,
                'billing_generation': (
                    ledger.get('allowance_billing_started_at')
                    if ledger.get('usage_committed_at') is not None
                    else datetime.fromtimestamp(now, timezone.utc)
                ),
            }
        stamp = datetime.fromtimestamp(now, timezone.utc)
        updates = {}
        if int(seconds) - int(charged) > 0 and ledger.get('status') != 'completed':
            # Lane 6 ruling B(a): bill a cap-hold unit to its funded month across a rollover.
            stamp = usage_stamp(stamp, intake.get('usage_period'))
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
            'billing_generation': (
                ledger.get('allowance_billing_started_at')
                if ledger.get('usage_committed_at') is not None
                else datetime.fromtimestamp(now, timezone.utc)
            ),
        }

    def complete(
        self, segment_id: str, binding: ProjectionBinding, now: float, accounting: dict, *, policy=None
    ) -> dict | None:
        """Complete only after every bound sibling persisted and marked enrichment."""
        policy = policy or self.policy(segment_id)
        coalescing_receipts: list[tuple[str, str]] = []

        @firestore.transactional
        def commit(transaction):
            coalescing_receipts.clear()
            session = self.session(segment_id, binding, now, policy=policy)
            session.prepare(transaction, replay=False)
            members = coalescing_completion.prepare(
                self.client, self.store.namespace, transaction, binding, session.ledger
            )
            coalescing_receipts.extend(
                ('intakes', member['job_id']) for member in (session.ledger.get('coalescing') or {}).get('members', [])
            )
            receipts = []
            live_siblings = []
            erased_count = 0
            captured_seconds = 0.0
            terminal_empty_count = 0
            for sibling in binding.segment_ids:
                job = self.ref('jobs', sibling).get(transaction=transaction).to_dict() or {}
                entry = self.ref('results', sibling).get(transaction=transaction).to_dict() or {}
                from utils.batch_pipeline.input_retention import input_expiring

                if artifact_missing(job) or input_expiring(job):
                    return None, False, 0
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
            # This is a job-wide decision after collecting every sibling/part.
            # A no-text receipt must suppress IDs from parts assigned earlier.
            source_deleted = any(receipt.get('disposition') == 'source_deleted' for receipt in receipts)
            new, updated = self._visible(transaction, binding, receipts)
            superseded_count = sum(receipt.get('disposition') == 'superseded' for receipt in receipts)
            deleted_output_count = sum(receipt.get('disposition') == 'output_deleted' for receipt in receipts)
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
                    if new
                    or updated
                    or erased_count
                    or terminal_empty_count
                    or superseded_count
                    or deleted_output_count
                    else 'expected_silence'
                ),
            }
            if terminal_empty_count:
                result['no_recoverable_speech_segments'] = terminal_empty_count
            if superseded_count:
                result['superseded_segments'] = superseded_count
            if deleted_output_count:
                result['deleted_output_segments'] = deleted_output_count
            if source_deleted:
                result['reason_code'] = 'source_deleted'
            elif (
                not new
                and not updated
                and any(receipt.get('privacy_reason') == 'conversation_deleted' for receipt in receipts)
            ):
                result['reason_code'] = 'conversation_deleted'
            if session.ledger.get('status') == 'completed':
                old = session.ledger.get('result')
                if not isinstance(old, dict) or not is_valid_completed_sync_content_result(old):
                    raise ProjectionBlocked('invalid existing ledger completion')
                if source_deleted:
                    suppressed = {**old, 'new_memories': [], 'updated_memories': [], 'reason_code': 'source_deleted'}
                    if suppressed != old:
                        # Repair an older completion's output only. Its usage
                        # and original part receipts remain unchanged.
                        transaction.update(session.ledger_ref, {'result': suppressed})
                        for sibling in live_siblings:
                            transaction.update(self.ref('jobs', sibling), {'client_result': suppressed})
                        # This job was already terminated. Repairing its output
                        # is not a new completion and must not count again.
                        coalescing_completion.write(transaction, members, suppressed, now)
                        return suppressed, False, 0
                    coalescing_completion.write(transaction, members, suppressed, now)
                    return suppressed, False, 0
                if deleted_output_count:
                    # Preserve historical usage; publish only destinations that
                    # remain visible after the user's output deletion.
                    old = {
                        **old,
                        'new_memories': new,
                        'updated_memories': updated,
                        'deleted_output_segments': deleted_output_count,
                    }
                coalescing_completion.write(transaction, members, old, now)
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
            if not source_deleted:
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
            coalescing_completion.write(transaction, members, result, now)
            for sibling in live_siblings:
                # All assignment/enrichment receipts now exist. Wake held
                # siblings in the same durable completion, including a crash
                # before client publication or completion retention.
                transaction.update(
                    self.ref('results', sibling),
                    {'projection_state': 'ready', **projection_finish_state_fields('ready', now)},
                )
                transaction.update(self.ref('jobs', sibling), {'client_status': 'completed', 'client_result': result})
            return result, True, captured_seconds

        with nullcontext() if accounting.get('source_deleted') else writing('usage_month_cache', binding.owner_id):
            result, changed, seconds = self.run(commit, policy=policy)
        self._mirror(binding, coalescing_receipts)
        if result is not None and result.get('reason_code') != 'source_deleted':
            self._settle_allowance(binding, now, accounting, binding.segment_ids)
        if changed:
            self._observe_transcription(binding, now, accounting, result)
            if result.get('reason_code') == 'source_deleted':
                SOURCE_DELETED_JOBS.inc()
                logger.info('event=batch_projection action=completion outcome=source_deleted')
            record_correctness('projection_completed', seconds=seconds)
        return result

    def _visible(
        self, transaction, binding: ProjectionBinding, receipts, *, source_deleted=False
    ) -> tuple[list[str], list[str]]:
        """Earlier receipt IDs can have become bridge donors. Follow the same
        server redirects, retaining only visible canonical IDs."""
        # Both full and partial completion pass their aggregated receipts here.
        if source_deleted or any(receipt.get('disposition') == 'source_deleted' for receipt in receipts):
            if not projection_source_deleted_enabled():
                raise ProjectionBlocked('privacy disposition requires a source deletion tombstone')
            return [], []
        mapped = []
        outputs = [output for receipt in receipts for output in (receipt.get('size_rollover_outputs') or [receipt])]
        for receipt in outputs:
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
            queue_increment(
                transaction,
                self.client.collection('users').document(binding.owner_id),
                datetime.strptime(accounting['hour'], '%Y-%m-%d-%H'),
                accounting['updates'],
            )
        # Every charge boundary and when it committed, so fair use can re-issue
        # each recent step's once-key: a write lost after any earlier commit
        # still lands on a later attempt while that key is live.
        steps, times = extend_chain(*(charge_chain(ledger) if partial else ([0.0], [])), seconds, now)
        # Observer provenance only: the existing hourly write above remains the
        # billing authority. Unknown pre-rollout partials remain unobserved.
        previous_billed = ledger.get('allowance_billed_seconds') if partial else 0
        billed = None
        if type(previous_billed) is int and 0 <= previous_billed <= int(charged):
            billed = previous_billed + (int(seconds) - int(charged) if accounting['updates'] else 0)
        transaction.update(
            ledger_ref,
            {
                'usage_committed_at': datetime.fromtimestamp(now, timezone.utc),
                'usage_committed_seconds': seconds,
                'usage_steps': steps,
                'usage_step_times': times,
                'allowance_billed_seconds': billed,
                'allowance_billing_started_at': (
                    ledger.get('allowance_billing_started_at') if partial else datetime.fromtimestamp(now, timezone.utc)
                ),
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
                return None, False, []
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
            settled_ids = []
            source_deleted = False
            erased_count = terminal_empty_count = missing_count = 0
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
                parts = entry.get('projection_parts')
                # A held entry can still contain a settled deletion part. Do
                # not lose its privacy fence when skipping its output below.
                source_deleted = source_deleted or any(
                    part.get('disposition') == 'source_deleted'
                    for part in (parts.values() if parts else [entry.get('projection') or {}])
                )
                if not entry and held_without_recovery(job):
                    held += 1
                    missing_count += artifact_missing(job)
                    continue
                if entry and assignment_held_without_recovery(job, entry):
                    held += 1
                    continue
                receipt = entry.get('projection') or {}
                if receipt.get('state') != 'ready':
                    return None, False, []
                if entry.get('result', {}).get('outcome') == 'no_recoverable_speech':
                    terminal_empty_count += 1
                seconds += receipt.get('speech_seconds', 0.0)
                settled_ids.append(sibling)
                parts = entry.get('projection_parts')
                receipts.extend(parts.values() if parts else [receipt])
            if not held:
                return None, False, []
            new, updated = self._visible(transaction, binding, receipts, source_deleted=source_deleted)
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
            if missing_count:
                # This publishes siblings while keeping the upload unacknowledged.
                result['reason_code'] = ARTIFACT_MISSING_REASON
            if source_deleted:
                result['reason_code'] = 'source_deleted'
            if terminal_empty_count:
                result['no_recoverable_speech_segments'] = terminal_empty_count
            superseded_count = sum(receipt.get('disposition') == 'superseded' for receipt in receipts)
            if superseded_count:
                result['superseded_segments'] = superseded_count
            if ledger.get('status') == BATCH_PARTIAL_STATUS and ledger.get('result') == result:
                return (result, ([0.0], []) if source_deleted else charge_chain(ledger)), False, settled_ids
            if seconds != accounting['seconds']:
                raise ProjectionBlocked('speech accounting changed during completion')
            chain = charge_chain(ledger) if ledger.get('status') == BATCH_PARTIAL_STATUS else ([0.0], [])
            if not source_deleted:
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
            return (result, ([0.0], []) if source_deleted else extend_chain(*chain, seconds, now)), True, settled_ids

        with nullcontext() if accounting.get('source_deleted') else writing('usage_month_cache', binding.owner_id):
            outcome, changed, settled_ids = self.run(commit)
        if outcome is not None and outcome[0].get('reason_code') != 'source_deleted':
            self._settle_allowance(binding, now, accounting, settled_ids)
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

    Its recovery settled without words or hit the hard independent duration
    limit before spending (``failed_held``), or its
    recorded recovery policy is off and no paid call was ever authorized. Either
    way its encrypted audio stays server-side for a reviewed operator redrive.
    """
    from config.policy import RecoveryPolicy

    retained_dead = job.get('state') == 'dead' and job.get('dead_letter_reason') in {'held_expired', 'input_expiring'}
    if (job.get('state') != 'quarantined' and not retained_dead) or job.get('result'):
        return False
    if any(
        isinstance(job.get(key), dict) and job[key].get('state') not in {'completed', 'failed_held'}
        for key in OPERATOR_INTENTS
    ):
        return False
    if retained_dead or job.get('recovery_state') == 'failed_held':
        return True
    raw = (job.get('policy_parts') or {}).get('recovery')
    return (
        job.get('recovery_state') == 'held'
        and not job.get('recovery')
        and isinstance(raw, dict)
        and not RecoveryPolicy.from_dict(raw).recovery_enabled
    )


def assignment_held_without_recovery(job: dict, entry: dict) -> bool:
    """An assignment-quarantined unit that nothing automatic will change.

    The quarantined receipt is replay-fenced and the job is recovery-held: no
    sweep reassigns the row and no worker redrive is pending. Only a reviewed
    operator redrive (for example after a discarded record is restored) can
    move it; until then its committed result and encrypted audio stay put.
    """
    if (entry.get('projection') or {}).get('state') != 'quarantined':
        return False
    if job.get('recovery_state') != 'held':
        return False
    return not any(
        isinstance(job.get(key), dict) and job[key].get('state') not in {'completed', 'failed_held'}
        for key in OPERATOR_INTENTS
    )


class _ClientTransaction:
    """A raw Firestore transaction with the client that owns it, for ``Outbox.enqueue(tx=...)``."""

    def __init__(self, client, transaction):
        self.client = client
        self.transaction = transaction
