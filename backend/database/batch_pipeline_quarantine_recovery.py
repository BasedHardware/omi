"""Per-unit handoff; ordinary worker tokens and upload ownership never transfer."""

import math
from typing import Any
from uuid import uuid4

from database.firestore_read_origin import read_origin
from database.batch_pipeline_recovery_fence import RecoveryFence
from database.batch_pipeline_policy import (
    PROCESS_ENVIRONMENT,
    load_stage_policy,
    stage_in_transaction,
    record_policy_observations,
)
from database.batch_pipeline_projection_protocol import ProjectionBlocked, normalized_binding
from config.batch_language_recovery import MAX_AUDIO_SECONDS, language_guarded
from config.batch_paid_attempt import attempted, renewed, retryable
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import WorkResult, held_vad_census, held_silence_allowed, held_result_allowed
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.batch_pipeline.input_retention import held_input_leg, staged_at, staged_enqueue, TERMINAL_SECONDS
from config.batch_pipeline import batch_held_dead_letter_enabled, HELD_DEAD_LETTER_SECONDS

# A receipt proves words existed, but deliberately contains no transcript.
# Permit one replacement recognition only after the original intent's dwell.
MISSING_RESULT_DWELL_SECONDS = 900
MAX_MISSING_RESULT_RETRIES = 1


def has_words_receipt(marker):
    receipts = marker.get('recognizers') or {}
    if not isinstance(receipts, dict):
        return False
    return any(
        isinstance(receipt, dict)
        and receipt.get('provider') == provider
        and receipt.get('outcome') == 'words'
        and type(receipt.get('word_count')) is int
        and receipt['word_count'] > 0
        for provider, receipt in receipts.items()
        if provider in {'modulate', 'soniox'}
    )


class RecoveryStore(RecoveryFence):
    # Serving workers resolve an unpinned part from their own env; operator
    # subclasses replace this with explicit server settings or None (refuse).
    server_flags: Any = PROCESS_ENVIRONMENT

    def expire_held(self, segment_id, now):
        if not batch_held_dead_letter_enabled():
            return 'disabled'

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            if expire_input_in_transaction(tx, job, now):
                return 'expired'
            return expire_held_in_transaction(tx, job, now)

        return self.store.run(commit)

    def requeue_quarantined(self, segment_id, now, *, dead_before=None, expected_job=None):
        """Operator and nightly entry: retain the content/privacy ownership CAS.

        Emit only a committed, newly spent held re-drive. Staging-input repairs
        (expected_job) do not consume grants or feed production paging.
        """

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            if expected_job is not None and job != expected_job:
                return None
            if dead_before is not None:
                expired_at = job.get('held_expired_at')
                if (
                    job.get('state') != 'dead'
                    or job.get('dead_letter_reason') != 'held_expired'
                    or isinstance(expired_at, bool)
                    or not isinstance(expired_at, (int, float))
                    or not math.isfinite(expired_at)
                    or expired_at >= dead_before
                ):
                    return None
            return Scheduler.requeue_quarantined_in_transaction(tx, job, now, account=expected_job is None)

        outcome = self.store.run(commit)
        if outcome is not None and outcome.spent:
            from utils.backlog_metrics import record_transition

            record_transition('held_redrive_budget_spent')
        return outcome is not None

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

    def start(
        self, segment_id, token, now, *, provider="legacy_sync", operator_paid_attempt=False, local_silence=False
    ):
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
            if local_silence:
                if language_guarded(job) or job['recovery'].get('recognizers') or operator_paid_attempt:
                    raise ValueError('unattempted local silence required')
                # provider names the selected route, not an observed call. This
                # token-bound decision skips STT entirely, even if storage or
                # settle must later reconcile the deterministic result object.
                job['recovery']['no_vendor_call'] = {
                    'version': 1,
                    'reason': 'strict_vad_silence',
                    'vad_speech_seconds': 0,
                }
            job['recovery']['provider'] = provider
            job['recovery']['started_at'] = now
            if operator_paid_attempt:
                attempted(job['recovery'], 'soniox', max_attempts=2)
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

    def retry_missing_result(self, segment_id, token, now):
        """Requeue a words-without-object intent once; fence every old writer.

        Called only after an authorized artifact lookup found no result. This
        transaction rechecks custody, privacy, ownership, dwell and the receipt.
        It never calls a provider or reopens an explicit operator paid attempt.
        """
        next_token = uuid4().hex

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            marker = job.get('recovery') or {}
            if (
                job.get('state') != 'quarantined'
                or job.get('quarantine_reason') != 'worker_failed'
                or job.get('recovery_state') != 'running'
                or marker.get('token') != token
                or now - marker.get('started_at', now) <= MISSING_RESULT_DWELL_SECONDS
                or not has_words_receipt(marker)
                or job.get('result')
                or existing
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
                or job.get('speech_redrive')
                or job.get('silence_disposition')
                or job.get('terminal_disposition')
            ):
                return 'held'
            retries = marker.get('missing_result_retries', 0)
            if type(retries) is not int or not 0 <= retries < MAX_MISSING_RESULT_RETRIES or marker.get('paid_state'):
                # Preserve custody and the words evidence, but stop spending.
                # This is a local result failure, not an abandoned recognizer.
                marker.update(settled_at=now, failure={'stage': 'payload_validation', 'reason': 'operation_failed'})
                job['recovery_state'] = 'failed_held'
                if batch_held_dead_letter_enabled():
                    job['held_deadline_at'] = now + HELD_DEAD_LETTER_SECONDS
                tx.put('jobs', segment_id, job)
                return 'exhausted'
            marker['missing_result_history'] = [
                {key: marker[key] for key in ('token', 'started_at', 'recognizers') if key in marker}
            ]
            marker.update(token=next_token, prepared_at=now, missing_result_retries=retries + 1)
            for key in ('started_at', 'settled_at', 'failure', 'recognizers', 'provider', 'no_vendor_call'):
                marker.pop(key, None)
            job['recovery_state'] = 'prepared'
            tx.put('jobs', segment_id, job)
            return 'requeued'

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
            if batch_held_dead_letter_enabled():
                job['held_deadline_at'] = now + HELD_DEAD_LETTER_SECONDS
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

    def hold_invalid_manifest(self, segment_id, token, now, *, audio_uri):
        """Retain a unit whose stored manifest can never materialize, without a paid intent.

        failed_held leaves the recovery candidate set, so neither a task retry nor
        the sweep re-reads it. The manifest and its sources stay in place."""

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            if (
                job.get('state') != 'quarantined'
                or job.get('quarantine_reason') != 'worker_failed'
                or job.get('recovery_state') != 'prepared'
                or job.get('recovery', {}).get('token') != token
                or job.get('recovery', {}).get('started_at') is not None
                or job.get('audio_uri') != audio_uri
                or job.get('result')
                or existing
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
            ):
                return False
            job['recovery_state'] = 'failed_held'
            if batch_held_dead_letter_enabled():
                job['held_deadline_at'] = now + HELD_DEAD_LETTER_SECONDS
            job['recovery'].update(settled_at=now, refusal={'reason': 'invalid_retained_manifest'})
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def start_duration_limited(self, segment_id, token, now, *, audio_uri, audio_seconds, operator_paid_attempt=False):
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
            if operator_paid_attempt:
                attempted(recovery, 'soniox', max_attempts=2)
            job['recovery_state'] = 'running'
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def retry_paid_takeover(self, segment_id, token, now):
        """One explicit operator retry, with a new token fencing late writers."""
        next_token = uuid4().hex

        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            marker = job.get('recovery') or {}
            if (
                marker.get('token') != token
                or not retryable(marker, job.get('recovery_state'))
                or not language_guarded(job)
                or marker.get('epoch') != 1
                or job.get('state') != 'quarantined'
                or job.get('quarantine_reason') != 'worker_failed'
                or job.get('result')
                or existing
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
                or job.get('speech_redrive')
                or job.get('silence_disposition')
                or job.get('terminal_disposition')
            ):
                return None
            job['recovery'] = renewed(marker, next_token)
            job['recovery'].update(started_at=now)
            attempted(job['recovery'], 'soniox')
            job['recovery_state'] = 'running'
            tx.put('jobs', segment_id, job)
            return next_token

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
        previous_token=None,
    ):
        def commit(tx):
            job, _ = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            marker = job.get('recovery') or {}
            # A replacement may adopt its predecessor's late encrypted result
            # without starting another paid intent. CAS against prepared keeps
            # adoption and the replacement's start mutually exclusive.
            previous_result = (
                previous_token is not None
                and job.get('recovery_state') == 'prepared'
                and result_uri is not None
                and failure is None
                and any(
                    entry.get('token') == previous_token and has_words_receipt(entry)
                    for entry in marker.get('missing_result_history', [])
                )
            )
            if (
                job.get('state') != 'quarantined'
                or (job.get('recovery_state') != 'running' and not previous_result)
                or (previous_token is not None and not previous_result)
                or marker.get('token') != token
                or job.get('result')
                or existing
            ):
                return False, 0
            # A receipt may arrive after the caller's artifact/read snapshot.
            # Never let a stale abandon decision erase newly recorded words.
            if failure == {'stage': 'provider', 'reason': 'abandoned_running'} and has_words_receipt(job['recovery']):
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
                if batch_held_dead_letter_enabled():
                    job['held_deadline_at'] = now + HELD_DEAD_LETTER_SECONDS
                if failure:
                    from utils.batch_pipeline.recovery_disposition import STAGES, REASONS

                    if failure.get('stage') not in STAGES or failure.get('reason') not in REASONS:
                        raise ValueError('closed recovery failure required')
                    job['recovery']['failure'] = dict(failure)
            else:
                owner = tx.get('owners', owner_key(job['owner_id']))
                job.update(
                    result=WorkResult(segment_id, result_uri, outcome).to_dict(),
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


def expire_input_in_transaction(tx, job, now):
    """Use the existing held scan and content/privacy CAS; never delete retained artifacts."""
    from config.refactor_modes import batch_input_expiring_enabled
    from utils.batch_pipeline.input_retention import held_input_leg, staged_enqueue, TERMINAL_SECONDS, REASON
    from database.batch_pipeline_projection import assignment_held_without_recovery

    if not batch_input_expiring_enabled():
        return False
    stamp = staged_enqueue(job)
    leg = held_input_leg(job)
    lease = job.get('lease_until', 0)
    if (
        stamp is None
        or not leg
        or not math.isfinite(now)
        or now < stamp + TERMINAL_SECONDS
        or job.get('token')
        or type(lease) not in (int, float)
        or not math.isfinite(lease)
        or lease > now
    ):
        return False
    if leg == 'gpu':
        if not Scheduler.held_requeue_eligible(tx, job, now, allow_dead=False):
            return False
    else:
        entry = tx.get('results', job['segment_id'])
        receipts = [entry.get('projection') or {}, *(entry.get('projection_parts') or {}).values()]
        if (
            entry.get('projection_state') != 'quarantine_held'
            or entry.get('owner_key') != owner_key(job['owner_id'])
            or entry.get('segment_id') != job['segment_id']
            or entry.get('projection_privacy_refusal')
            or any(part.get('privacy_reason') for part in receipts)
            or not any(
                part.get('disposition') == 'ambiguous_generation'
                and assignment_held_without_recovery(job, {**entry, 'projection': part})
                for part in receipts
            )
        ):
            return False
    if leg == 'gpu':
        binding = normalized_binding(job['projection_binding'])
        if not (binding.native_record or binding.record_origin or binding.partial_record):
            ledger_key = f'{binding.owner_id}/{binding.content_id}'
            ledger = tx.get('content', ledger_key)
            ledger['artifact_missing_units'] = sorted(
                set(ledger.get('artifact_missing_units') or []) | {job['segment_id']}
            )
            tx.put('content', ledger_key, ledger)
    job.update(
        state='dead',
        merge_pending=leg == 'gpu',
        dead_letter_reason=REASON,
        input_expiring_at=now,
        input_expiring_leg=leg,
    )
    tx.put('jobs', job['segment_id'], job)
    return True


def expire_held_in_transaction(tx, job, now):
    """CAS a dormant compute hold into a retained, reasoned dead letter.

    No artifact IO, TTL or conversation write. Callers retain RecoveryStore.checked
    and the store's commit-boundary privacy fence. Old rows get a full window.
    """
    if not batch_held_dead_letter_enabled():
        return 'disabled'
    if not Scheduler.held_requeue_eligible(tx, job, now, allow_dead=False):
        return 'held'
    deadline = job.get('held_deadline_at')
    if deadline is None:
        job['held_deadline_at'] = now + HELD_DEAD_LETTER_SECONDS
        tx.put('jobs', job['segment_id'], job)
        return 'stamped'
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
        return 'held'  # Malformed metadata is not permission to expire custody.
    if deadline > now:
        return 'held'
    # The pre-existing redrive_dead route requires merge_pending. Preserve that
    # recovery contract even if this feature is disabled or its code reverted.
    job.update(state='dead', merge_pending=True, dead_letter_reason='held_expired', held_expired_at=now)
    tx.put('jobs', job['segment_id'], job)
    return 'expired'


def dead_held_candidates(client, namespace, limit=32, *, after_id=None):
    """Only this reason is nightly redriven; historical dead stock is untouched."""
    collection = client.collection(f'{namespace}_jobs')
    query = collection.where('state', '==', 'dead').where('dead_letter_reason', '==', 'held_expired')
    query = query.order_by('__name__')
    if after_id is not None:
        query = query.start_after({'__name__': collection.document(after_id)})
    return [(doc.id, doc.to_dict() or {}) for doc in query.limit(max(1, min(limit, 64))).stream()]


def held_expired_stock(client, namespace):
    query = client.collection(f'{namespace}_jobs').where('state', '==', 'dead')
    jobs = query.where('dead_letter_reason', '==', 'held_expired').count().get()[0][0].value
    results = client.collection(f'{namespace}_results').where('projection_state', '==', 'quarantine_held')
    return jobs + results.where('held_expired_reason', '==', 'held_expired').count().get()[0][0].value


@read_origin('job:batch_pipeline_quarantine_recovery:recovery_candidates')
def recovery_candidates(client, namespace: str, owner_id: str | None, limit: int = 10, *, after_id: str | None = None):
    """Only unattempted or reconcilable units; failed STT never hot-loops."""
    collection = client.collection(f'{namespace}_jobs')
    query = collection
    if owner_id is not None:
        query = query.where('owner_id', '==', owner_id)
    # A quarantine-held projection also marks its committed job recovery_state=held
    # for the held-partial scan; prepare() refuses those, so they must not fill the page.
    # Equality-only filters: served by single-field index merging, no composite.
    query = query.where('state', '==', 'quarantined')
    query = query.where('recovery_state', 'in', ['held', 'prepared', 'running'])
    if owner_id is None:
        # A document-reference cursor requires no extra document read.
        query = query.order_by('__name__')
        if after_id is not None:
            query = query.start_after({'__name__': collection.document(after_id)})
    return [(doc.id, (doc.to_dict() or {})['owner_id']) for doc in query.limit(max(1, min(limit, 64))).stream()]


@read_origin('job:batch_pipeline_quarantine_recovery:held_candidates')
def held_candidates(client, namespace: str, limit: int = 32, *, after_id: str | None = None):
    """Held/failed_held units in document order for the partial scan; eligibility is rechecked per upload."""
    collection = client.collection(f'{namespace}_jobs')
    query = collection.where('recovery_state', 'in', ['held', 'failed_held']).order_by('__name__')
    if after_id is not None:
        # A document-reference cursor requires no extra document read.
        query = query.start_after({'__name__': collection.document(after_id)})
    return [(doc.id, doc.to_dict() or {}) for doc in query.limit(max(1, min(limit, 64))).stream()]


@read_origin('job:batch_pipeline_quarantine_recovery:input_expiring_candidates')
def input_expiring_candidates(client, namespace, now, *, after=None):
    """Two indexed clock streams, each at most 128 snapshots; no legacy backfill.

    Legacy enqueue rows and stamped replacements have different expiry anchors.
    Advance independent age cursors even over filtered/fenced rows: fresh
    replacements in the legacy index must never pin its oldest prefix.
    """
    collection = client.collection(f'{namespace}_jobs')
    cutoff = now - TERMINAL_SECONDS
    candidates, cursors = [], {}
    for field in ('enqueued_at', 'audio_staged_at'):
        query = (
            collection.where('state', 'in', ['quarantined', 'committed'])
            .where('recovery_state', 'in', ['held', 'failed_held'])
            .where(field, '<=', cutoff)
            .order_by(field)
            .order_by('__name__')
        )
        cursor = (after or {}).get(field)
        if cursor:
            query = query.start_after({field: cursor['at'], '__name__': collection.document(cursor['id'])})
        docs = list(query.limit(128).stream())
        for doc in docs:
            job = doc.to_dict() or {}
            # Route by clock validity, not field presence. Malformed replacements
            # retain the earlier enqueue protection, without duplicate candidates.
            restaged = staged_at(job) is not None
            if field == 'enqueued_at' and restaged:
                continue
            if field == 'audio_staged_at' and not restaged:
                continue
            try:
                stamp, leg = staged_enqueue(job), held_input_leg(job)
            except (TypeError, AttributeError):
                continue  # Malformed eligibility metadata cannot pin the age cursor.
            if stamp is not None and stamp <= cutoff and leg:
                candidates.append((doc.id, job))
        cursors[field] = {'at': docs[-1].to_dict()[field], 'id': docs[-1].id} if len(docs) == 128 else None
    return sorted(candidates, key=lambda pair: (staged_enqueue(pair[1]), pair[0])), cursors


def cancel_fenced_recovery(store, segment_id):
    """Revocation-only write, allowed after privacy rejects ordinary job writes."""
    if hasattr(store, 'cancel_fenced_recovery'):
        return store.cancel_fenced_recovery(segment_id)
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
                return WorkResult(segment_id, result_uri, 'silence').matches_persisted(job.get('result'))
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
                result=WorkResult(segment_id, result_uri, 'silence').to_dict(),
            )
            tx.put('owners', owner_key(job['owner_id']), owner)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)
