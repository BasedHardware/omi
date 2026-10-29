"""Per-unit handoff; ordinary worker tokens and upload ownership never transfer."""

from dataclasses import asdict
import math
from typing import Any
from uuid import uuid4

from database.batch_pipeline_policy import (
    PROCESS_ENVIRONMENT,
    load_stage_policy,
    stage_in_transaction,
    record_policy_observations,
)
from database.batch_pipeline_projection_protocol import ProjectionBlocked, normalized_binding
from database.sync_ledger import batch_projection_ledger_owner_matches
from config.batch_language_recovery import MAX_AUDIO_SECONDS, language_guarded
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import WorkResult, held_vad_census, held_silence_allowed, held_result_allowed
from utils.batch_pipeline.scheduler import owner_key


class RecoveryStore:
    # Serving workers resolve an unpinned part from their own env; operator
    # subclasses replace this with explicit server settings or None (refuse).
    server_flags: Any = PROCESS_ENVIRONMENT

    def __init__(self, store: Any):
        self.store = store

    def checked(
        self,
        tx,
        segment_id,
        *,
        allow_completed_silence=False,
        allow_completed_speech_redrive=False,
        allow_completed_terminal=False,
        allow_completed_recovery=False,
    ):
        job = tx.get('jobs', segment_id)
        if not job or not job.get('projection_binding'):
            raise ProjectionBlocked('recovery intake binding required')
        binding = normalized_binding(job['projection_binding'])
        from utils.sync.capture import chunk_identity

        ids = set(job.get('conversation_ids') or [])
        ids.add(
            chunk_identity(
                binding.owner_id, binding.source, binding.client_device_id, binding.is_locked, job['capture_at']
            )
        )
        ids.update(value for value in (job.get('conversation_id'), binding.target_conversation_id) if value)
        tx.check_privacy(binding.owner_id, ids, binding.privacy_generation)
        ledger = tx.get('content', f'{binding.owner_id}/{binding.content_id}')
        if (
            job.get('owner_id') != binding.owner_id
            or job.get('privacy_generation') != binding.privacy_generation
            or (job.get('recovery') and job['recovery'].get('privacy_generation') != binding.privacy_generation)
            or segment_id not in binding.segment_ids
            or ledger.get('dispatch_protocol') != 'batch_v1'
            or ledger.get('batch_pipeline')
            != {'protocol_version': 1, 'namespace': self.store.namespace, 'segment_ids': list(binding.segment_ids)}
            or not (
                batch_projection_ledger_owner_matches(ledger, binding.job_id, binding.run_token, binding.run_epoch)
                or (
                    allow_completed_silence
                    and ledger.get('status') == 'completed'
                    and ledger.get('job_id') == binding.job_id
                    and job.get('silence_disposition', {}).get('state') == 'completed'
                    and job.get('result', {}).get('outcome') == 'silence'
                )
                or (
                    allow_completed_speech_redrive
                    and ledger.get('status') == 'completed'
                    and ledger.get('job_id') == binding.job_id
                    and job.get('speech_redrive', {}).get('state') == 'completed'
                    and job.get('result', {}).get('outcome') in {'success', 'no_recoverable_speech', 'silence'}
                )
                or (
                    allow_completed_recovery
                    and ledger.get('status') == 'completed'
                    and ledger.get('job_id') == binding.job_id
                    and job.get('recovery_state') == 'recovered'
                    and bool(job.get('result'))
                )
                or (
                    allow_completed_terminal
                    and ledger.get('status') == 'completed'
                    and ledger.get('job_id') == binding.job_id
                    and job.get('terminal_disposition', {}).get('state') == 'completed'
                    and job.get('result', {}).get('outcome') == job['terminal_disposition'].get('outcome')
                )
            )
        ):
            raise ProjectionBlocked('recovery content owner lost')
        return job, binding

    def prepare(self, segment_id, owner_id, now):
        load_stage_policy(self.store, segment_id, 'recovery', server_flags=self.server_flags)
        # Generated outside the retryable transaction; a lost reply is reconciled
        # by rereading this same intent, never by issuing a second provider call.
        token = uuid4().hex

        def commit(tx):
            job, binding = self.checked(tx, segment_id)
            result = tx.get('results', segment_id)
            if (
                binding.owner_id != owner_id
                or job.get('state') != 'quarantined'
                or job.get('quarantine_reason') != 'worker_failed'
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
                or job.get('result')
                or result
            ):
                return None
            if job.get('recovery_state') == 'held' and not job.get('recovery'):
                job['recovery'] = {
                    'token': token,
                    'epoch': 1,
                    'privacy_generation': binding.privacy_generation,
                    'prepared_at': now,
                }
                job['recovery_state'] = 'prepared'
                tx.put('jobs', segment_id, job)
            return job if job.get('recovery_state') in {'prepared', 'running'} else None

        return self.store.run(commit)

    def claim_wake(self, segment_id, token, now, lease_seconds, *, queue='', expected_seq=0):
        """Reserve the next delivery wake for a prepared intent.

        Scheduling metadata only: it never authorizes a provider call (start()
        remains the sole paid-intent fence). Returns the new wake sequence, or
        None while a wake is still leased or another sweeper already advanced it
        (``expected_seq`` is a compare-and-set on the wake the caller inspected).
        """

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            if (
                job.get('state') != 'quarantined'
                or job.get('recovery_state') != 'prepared'
                or job.get('recovery', {}).get('token') != token
            ):
                return None
            wake = job.get('recovery_wake') or {}
            current = wake.get('seq', 0) if wake.get('token') == token else 0
            if current != expected_seq or (wake.get('token') == token and wake.get('wake_until', 0) > now):
                return None
            job['recovery_wake'] = {
                'token': token,
                'seq': current + 1,
                'wake_until': now + lease_seconds,
                'queue': queue,
            }
            tx.put('jobs', segment_id, job)
            return current + 1

        return self.store.run(commit)

    def extend_wake(self, segment_id, token, seq, now, lease_seconds, *, probe_error=False):
        """Keep wake ``seq`` leased because its task still exists (or custody is unknown)."""

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            wake = job.get('recovery_wake') or {}
            if (
                job.get('state') != 'quarantined'
                or job.get('recovery_state') != 'prepared'
                or job.get('recovery', {}).get('token') != token
                or wake.get('token') != token
                or wake.get('seq') != seq
                # A concurrent shorten (held delivery) or extend already stands.
                or wake.get('wake_until', 0) > now
            ):
                return False
            errors = wake.get('probe_errors', 0) + 1 if probe_error else 0
            job['recovery_wake'] = {**wake, 'wake_until': now + lease_seconds, 'probe_errors': errors}
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def shorten_wake(self, segment_id, seq, now, rewake_seconds):
        """Re-arm sooner after wake ``seq`` was delivered (or failed to enqueue)
        and left the intent prepared. Only that same wake is shortened, so a stale
        delivery never cuts the lease of a newer outstanding wake."""

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            wake = job.get('recovery_wake')
            if (
                not wake
                or job.get('state') != 'quarantined'
                or job.get('recovery_state') != 'prepared'
                or wake.get('token') != job.get('recovery', {}).get('token')
                or wake.get('seq') != seq
                # Already re-armed at least as soon. An expired lease is re-armed
                # too, so a custody probe racing this delivery cannot restore
                # the full lease (extend_wake skips a live wake_until).
                or now < wake.get('wake_until', 0) <= now + rewake_seconds
            ):
                return False
            job['recovery_wake'] = {**wake, 'wake_until': now + rewake_seconds}
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def start(self, segment_id, token, now, *, provider="legacy_sync"):
        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            result = tx.get('results', segment_id)
            if (
                job.get('state') != 'quarantined'
                or job.get('recovery_state') != 'prepared'
                or job.get('recovery', {}).get('token') != token
                or job.get('result')
                or result
                or job.get('token')
                or job.get('lease_until', 0) > now
            ):
                return False
            job['recovery_state'] = 'running'
            if provider not in {'legacy_sync', 'modulate'}:
                raise ValueError('closed recovery provider required')
            job['recovery']['provider'] = provider
            job['recovery']['started_at'] = now
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def observe_vad(self, segment_id, token, seconds):
        """A prepared intent can retain measured evidence without authorizing STT."""

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            if (
                job.get('state') != 'quarantined'
                or job.get('recovery_state') != 'prepared'
                or job.get('recovery', {}).get('token') != token
                or job.get('result')
            ):
                return False
            measured = held_vad_census(job, seconds)
            if job.get('measured_held_vad_speech_seconds') != measured:
                job['measured_held_vad_speech_seconds'] = measured
                tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def hold_duration_limit(self, segment_id, token, now, *, audio_uri, audio_seconds):
        """Retain an impossible independent recovery without starting a paid intent."""
        if not math.isfinite(audio_seconds) or not MAX_AUDIO_SECONDS < audio_seconds <= 7200:
            return False

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            if (
                job.get('state') != 'quarantined'
                or job.get('quarantine_reason') != 'worker_failed'
                or job.get('recovery_state') != 'prepared'
                or job.get('recovery', {}).get('token') != token
                or job.get('recovery', {}).get('started_at') is not None
                or not language_guarded(job)
                or job.get('audio_uri') != audio_uri
                or not math.isfinite(job['duration_seconds'])
                or abs(job['duration_seconds'] - audio_seconds) > 0.1
                or job.get('result')
                or existing
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
            ):
                return False
            job['recovery_state'] = 'failed_held'
            job['measured_held_vad_speech_seconds'] = held_vad_census(job, 0)
            job['recovery'].update(
                settled_at=now,
                refusal={
                    'reason': 'independent_duration_limit',
                    'max_audio_seconds': MAX_AUDIO_SECONDS,
                    'audio_seconds': audio_seconds,
                },
            )
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def start_duration_limited(self, segment_id, token, now, *, audio_uri, audio_seconds):
        """Operator take-over of a duration-limited intent: refusal -> running.

        The exact mirror of hold_duration_limit: only the never-started guarded
        intent that refusal settled, with no provider call, receipt or failure
        spent. One fenced transition straight into the running take-over, so a
        concurrent sweep cannot re-settle the refusal between reopen and start.
        A spent intent never reopens."""
        if not math.isfinite(audio_seconds) or not MAX_AUDIO_SECONDS < audio_seconds <= 7200:
            return False

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            recovery = job.get('recovery') or {}
            if (
                job.get('state') != 'quarantined'
                or job.get('quarantine_reason') != 'worker_failed'
                or job.get('recovery_state') != 'failed_held'
                or recovery.get('token') != token
                or recovery.get('started_at') is not None
                or recovery.get('provider') is not None
                or recovery.get('recognizers')
                or recovery.get('failure') is not None
                or recovery.get('refusal')
                != {
                    'reason': 'independent_duration_limit',
                    'max_audio_seconds': MAX_AUDIO_SECONDS,
                    'audio_seconds': audio_seconds,
                }
                or not language_guarded(job)
                or job.get('audio_uri') != audio_uri
                or not math.isfinite(job['duration_seconds'])
                or abs(job['duration_seconds'] - audio_seconds) > 0.1
                or job.get('result')
                or existing
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
            ):
                return False
            recovery.pop('refusal', None)
            recovery.pop('settled_at', None)
            recovery.update(provider='modulate', started_at=now)
            job['recovery_state'] = 'running'
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def settle(
        self,
        segment_id,
        token,
        now,
        result_uri=None,
        *,
        outcome="success",
        failure=None,
        measured_held_vad_speech_seconds=None,
        independent_silence=False,
    ):
        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            if (
                job.get('state') != 'quarantined'
                or job.get('recovery_state') != 'running'
                or job.get('recovery', {}).get('token') != token
                or job.get('result')
                or existing
            ):
                return False, 0
            census = held_vad_census(job, measured_held_vad_speech_seconds)
            if result_uri and not held_result_allowed(
                job, outcome, measured_held_vad_speech_seconds, independent=independent_silence
            ):
                if job.get('measured_held_vad_speech_seconds') != census:
                    job['measured_held_vad_speech_seconds'] = census
                    tx.put('jobs', segment_id, job)
                return False, 0
            job['measured_held_vad_speech_seconds'] = census
            if result_uri is None:
                job.update(recovery_state='failed_held')
                if failure:
                    from utils.batch_pipeline.recovery_disposition import STAGES, REASONS

                    if failure.get('stage') not in STAGES or failure.get('reason') not in REASONS:
                        raise ValueError('closed recovery failure required')
                    job['recovery']['failure'] = dict(failure)
            else:
                owner = tx.get('owners', owner_key(job['owner_id']))
                job.update(
                    result=asdict(WorkResult(segment_id, result_uri, outcome)),
                    state='result_ready',
                    ready_at=now,
                    merge_pending=True,
                    recovery_state='recovered',
                )
                owner['revision'] = owner.get('revision', 0) + 1
                tx.put('owners', owner_key(job['owner_id']), owner)
            job['recovery']['settled_at'] = now
            tx.put('jobs', segment_id, job)
            return True, job['duration_seconds'] if result_uri is not None else 0

        changed, seconds = self.store.run(commit)
        if changed and seconds:
            record_correctness(
                'no_recoverable_speech' if outcome == 'no_recoverable_speech' else 'recovered', seconds=seconds
            )
        return changed


def recovery_candidates(client, namespace: str, owner_id: str | None, limit: int = 10, *, after_id: str | None = None):
    """Only unattempted or reconcilable units; failed STT never hot-loops."""
    collection = client.collection(f'{namespace}_jobs')
    query = collection
    if owner_id is not None:
        query = query.where('owner_id', '==', owner_id)
    query = query.where('recovery_state', 'in', ['held', 'prepared', 'running'])
    if owner_id is None:
        # A document-reference cursor requires no extra document read.
        query = query.order_by('__name__')
        if after_id is not None:
            query = query.start_after({'__name__': collection.document(after_id)})
    return [(doc.id, (doc.to_dict() or {})['owner_id']) for doc in query.limit(max(1, min(limit, 64))).stream()]


def held_candidates(client, namespace: str, limit: int = 32, *, after_id: str | None = None):
    """Held/failed_held units in document order for the partial scan; eligibility is rechecked per upload."""
    collection = client.collection(f'{namespace}_jobs')
    query = collection.where('recovery_state', 'in', ['held', 'failed_held']).order_by('__name__')
    if after_id is not None:
        # A document-reference cursor requires no extra document read.
        query = query.start_after({'__name__': collection.document(after_id)})
    return [(doc.id, doc.to_dict() or {}) for doc in query.limit(max(1, min(limit, 64))).stream()]


def cancel_fenced_recovery(store, segment_id):
    """Revocation-only write, allowed after privacy rejects ordinary job writes."""
    from google.cloud import firestore
    from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed

    ref = store.client.collection(f'{store.namespace}_jobs').document(segment_id)

    @firestore.transactional
    def cancel(transaction):
        job = ref.get(transaction=transaction).to_dict() or {}
        if not job or not job.get('recovery'):
            return False
        binding = normalized_binding(job['projection_binding'])
        ids = [value for value in (job.get('conversation_id'), binding.target_conversation_id) if value]
        ids.extend(job.get('conversation_ids') or [])
        try:
            assert_batch_write_allowed(
                store.client,
                transaction,
                binding.owner_id,
                conversation_ids=ids,
                expected_generation=binding.privacy_generation,
            )
        except BatchPrivacyBlocked:
            transaction.update(ref, {'recovery_state': 'cancelled'})
            return True
        return False

    cancelled = cancel(store.client.transaction())
    if cancelled:
        from database.batch_pipeline_shadow_hook import mirror_refresh

        mirror_refresh(store.namespace, [('jobs', segment_id)])  # A2 shadow: no-op unless shadow mode
    return cancelled


class SilenceDispositionStore(RecoveryStore):
    """Explicit operator-only no-provider intent. The spent STT intent stays intact."""

    def __init__(self, store: Any, *, server_flags):
        """`server_flags` is the serving role's live settings for an unpinned unit,
        or None to refuse it; never this process's environment."""
        super().__init__(store)
        self.server_flags = server_flags

    def prepare_silence(self, segment_id, owner_id, plan_digest, now):
        from config.batch_pipeline import empty_asr_disposition_enabled

        if not empty_asr_disposition_enabled():
            raise ProjectionBlocked('disposition disabled')
        candidates, observations = {}, []
        token = uuid4().hex

        def commit(tx):
            observations.clear()
            job, binding = self.checked(tx, segment_id, allow_completed_silence=True)
            policy = stage_in_transaction(
                tx, job, 'recovery', candidates=candidates, observations=observations, server_flags=self.server_flags
            )
            if not policy.recovery_enabled:
                raise ProjectionBlocked('disposition disabled')
            existing = tx.get('results', segment_id)
            marker = job.get('silence_disposition') or {}
            if binding.owner_id != owner_id:
                raise ProjectionBlocked('disposition owner mismatch')
            if marker.get('plan_digest') == plan_digest and marker.get('state') == 'completed':
                return job
            if not held_silence_allowed(job, 0):
                raise ProjectionBlocked('held speech blocks no-provider silence')
            if (
                binding.owner_id != owner_id
                or job.get('state') != 'quarantined'
                or job.get('quarantine_reason') != 'worker_failed'
                or job.get('recovery_state') != 'failed_held'
                or not job.get('recovery', {}).get('settled_at')
                or job.get('speech_redrive')
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
                or job.get('result')
                or existing
            ):
                raise ProjectionBlocked('terminal held obligation required')
            if marker and (
                marker.get('plan_digest') != plan_digest
                or marker.get('privacy_generation') != binding.privacy_generation
            ):
                raise ProjectionBlocked('different disposition intent')
            if not marker:
                job['silence_disposition'] = {
                    'token': token,
                    'plan_digest': plan_digest,
                    'state': 'prepared',
                    'prepared_at': now,
                    'privacy_generation': binding.privacy_generation,
                }
                tx.put('jobs', segment_id, job)
            return job

        result = self.store.run(commit)
        record_policy_observations(observations)
        return result

    def complete_silence(
        self, segment_id, token, plan_digest, result_uri, now, *, measured_held_vad_speech_seconds=None
    ):
        from config.batch_pipeline import empty_asr_disposition_enabled

        if not empty_asr_disposition_enabled():
            return False

        def commit(tx):
            job, binding = self.checked(tx, segment_id, allow_completed_silence=True)
            existing = tx.get('results', segment_id)
            marker = job.get('silence_disposition') or {}
            if (
                marker.get('token') != token
                or marker.get('plan_digest') != plan_digest
                or marker.get('privacy_generation') != binding.privacy_generation
            ):
                return False
            if marker.get('state') == 'completed':
                return job.get('result') == asdict(WorkResult(segment_id, result_uri, 'silence'))
            if (
                job.get('state') != 'quarantined'
                or job.get('recovery_state') != 'failed_held'
                or marker.get('state') != 'prepared'
                or job.get('result')
                or existing
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
            ):
                return False
            census = held_vad_census(job, measured_held_vad_speech_seconds)
            if not held_silence_allowed(job, measured_held_vad_speech_seconds):
                if job.get('measured_held_vad_speech_seconds') != census:
                    job['measured_held_vad_speech_seconds'] = census
                    tx.put('jobs', segment_id, job)
                return False
            owner = tx.get('owners', owner_key(job['owner_id']))
            job['measured_held_vad_speech_seconds'] = held_vad_census(job, measured_held_vad_speech_seconds)
            owner['revision'] = owner.get('revision', 0) + 1
            marker.update(state='completed', completed_at=now)
            job.update(
                state='result_ready',
                ready_at=now,
                merge_pending=True,
                recovery_state='recovered',
                result=asdict(WorkResult(segment_id, result_uri, 'silence')),
            )
            tx.put('owners', owner_key(job['owner_id']), owner)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)
