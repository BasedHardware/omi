"""Non-paid terminal disposition CAS; immutable paid intents are never reset."""

from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4

from database.batch_pipeline_policy import load_stage_policy, stage_in_transaction, record_policy_observations
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.scheduler import owner_key

CANARY_OPERATION = 'david-held-gpu-redrive-20261017-v1'
EMPTY_FAILURE = {'stage': 'response_validation', 'reason': 'empty_asr'}


def spent_canary(job):
    recovery = job.get('recovery') or {}
    return (
        job.get('operator_redrive', {}).get('operation') == CANARY_OPERATION
        and job.get('recovery_state') == 'held'
        and recovery.get('epoch') == 1
        and bool(recovery.get('started_at'))
        and bool(recovery.get('settled_at'))
    )


def exhausted(job, historical_attestation=False):
    """Only a definite empty response, never a timeout/provider/unknown failure."""
    recovery, redrive = job.get('recovery') or {}, job.get('speech_redrive') or {}
    if redrive:
        return (
            redrive.get('state') == 'failed_held'
            and redrive.get('paid_epoch') == 2
            and redrive.get('provider') == 'modulate'
            and redrive.get('failure') == EMPTY_FAILURE
            and redrive.get('prior_recovery') == recovery
            and bool(redrive.get('settled_at'))
        )
    return (
        job.get('recovery_state') == 'failed_held'
        and recovery.get('failure') == EMPTY_FAILURE
        and bool(recovery.get('started_at'))
        and bool(recovery.get('settled_at'))
        and (recovery.get('provider') == 'modulate' or historical_attestation and not recovery.get('provider'))
    )


def intent_snapshot(job):
    snapshot = {k: job.get(k) for k in ('recovery', 'speech_redrive', 'operator_redrive', 'worker_empty_evidence')}
    # The old GPU canary has no epoch-2 intent at plan time. Its later paid
    # marker is fenced independently, and must not invalidate this plan replay.
    if job.get('operator_redrive', {}).get('operation') == CANARY_OPERATION:
        snapshot['speech_redrive'] = None
    return deepcopy(snapshot)


def idle(job, existing, now):
    return (
        job.get('state') == 'quarantined'
        and job.get('quarantine_reason') == 'worker_failed'
        and not job.get('token')
        and job.get('lease_until', 0) <= now
        and job.get('merge_pending') is False
        and not job.get('result')
        and not existing
        and not job.get('silence_disposition')
    )


class TerminalEmptyStore:
    def __init__(self, store, *, server_flags):
        """Operator-only. `server_flags` is the serving role's live settings for an
        unpinned unit, or None to refuse it; never this process's environment."""
        self.store = store
        self.server_flags = server_flags

    def checked(self, tx, sid):
        return RecoveryStore(self.store).checked(
            tx, sid, allow_completed_terminal=True, allow_completed_speech_redrive=True
        )

    def prepare(self, sid, uid, plan, snapshot, outcome, historical_attestation, now):
        candidates, observations = {}, []
        token = uuid4().hex

        def commit(tx):
            observations.clear()
            job, binding = self.checked(tx, sid)
            policy = stage_in_transaction(
                tx, job, 'recovery', candidates=candidates, observations=observations, server_flags=self.server_flags
            )
            if not policy.terminal_empty_disposition or not policy.recovery_enabled:
                raise ProjectionBlocked('terminal disposition disabled')
            existing = tx.get('results', sid)
            marker = job.get('terminal_disposition') or {}
            if (
                binding.owner_id != uid
                or intent_snapshot(job) != snapshot
                or outcome not in {'silence', 'no_recoverable_speech', 'canary_recovery'}
            ):
                raise ProjectionBlocked('terminal disposition ownership changed')
            if marker:
                if (
                    marker.get('plan_digest') != plan
                    or marker.get('outcome') != outcome
                    or marker.get('privacy_generation') != binding.privacy_generation
                    or marker.get('prior_intents') != snapshot
                    or marker.get('historical_attestation') != historical_attestation
                ):
                    raise ProjectionBlocked('different terminal disposition')
                return job
            if not idle(job, existing, now) or not (spent_canary(job) or exhausted(job, historical_attestation)):
                raise ProjectionBlocked('exhausted or spent canary required')
            if outcome == 'canary_recovery' and not spent_canary(job):
                raise ProjectionBlocked('unattempted canary epoch 2 required')
            if outcome == 'no_recoverable_speech' and not exhausted(job, historical_attestation):
                raise ProjectionBlocked('multilingual exhaustion required')
            if outcome == 'no_recoverable_speech' and not (
                job.get('worker_empty_evidence') == {'padded_retry': 'empty', 'version': 1}
                or historical_attestation
                and not job.get('worker_empty_evidence')
            ):
                raise ProjectionBlocked('padded retry evidence required')
            job['terminal_disposition'] = {
                'token': token,
                'plan_digest': plan,
                'outcome': outcome,
                'state': 'prepared',
                'privacy_generation': binding.privacy_generation,
                'prior_intents': snapshot,
                'historical_attestation': historical_attestation,
                'prepared_at': now,
            }
            tx.put('jobs', sid, job)
            return job

        result = self.store.run(commit)
        record_policy_observations(observations)
        return result

    def complete(self, sid, token, plan, uri, now):
        _, policy = load_stage_policy(self.store, sid, 'recovery', server_flags=self.server_flags)
        if policy is None or not policy.terminal_empty_disposition:
            return False

        def commit(tx):
            job, binding = self.checked(tx, sid)
            existing = tx.get('results', sid)
            marker = job.get('terminal_disposition') or {}
            if (
                not policy.recovery_enabled
                or marker.get('token') != token
                or marker.get('plan_digest') != plan
                or marker.get('privacy_generation') != binding.privacy_generation
                or marker.get('prior_intents') != intent_snapshot(job)
            ):
                return False, 0, None
            outcome = marker['outcome']
            result = asdict(WorkResult(sid, uri, outcome))
            if marker.get('state') == 'completed':
                return job.get('result') == result, 0, outcome
            if marker.get('state') != 'prepared' or not idle(job, existing, now):
                return False, 0, None
            owner = tx.get('owners', owner_key(binding.owner_id))
            owner['revision'] = owner.get('revision', 0) + 1
            marker.update(state='completed', completed_at=now)
            job.update(
                state='result_ready', merge_pending=True, recovery_state='recovered', result=result, ready_at=now
            )
            tx.put('owners', owner_key(binding.owner_id), owner)
            tx.put('jobs', sid, job)
            return True, job['duration_seconds'], outcome

        changed, seconds, outcome = self.store.run(commit)
        if changed and seconds:
            record_correctness(
                'no_recoverable_speech' if outcome == 'no_recoverable_speech' else 'recovered', seconds=seconds
            )
        return changed
