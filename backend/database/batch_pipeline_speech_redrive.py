"""Explicit epoch-2 operator intent; never reset or auto-scan a spent recovery."""

from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4

from config.policy import RecoveryPolicy
from database.batch_pipeline_policy import load_stage_policy, stage_in_transaction, record_policy_observations
from database.batch_pipeline_terminal_empty import spent_canary
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.recovery_disposition import STAGES, REASONS, padded_skipped
from utils.batch_pipeline.scheduler import owner_key

PAID_EPOCH = 2


class SpeechRedriveStore:
    def __init__(self, store, *, server_flags):
        """Operator-only. `server_flags` is the serving role's live settings for an
        unpinned unit, or None to refuse it; never this process's environment."""
        self.store = store
        self.server_flags = server_flags

    def checked(self, tx, segment_id):
        return RecoveryStore(self.store).checked(tx, segment_id, allow_completed_speech_redrive=True)

    @staticmethod
    def terminal(job, existing, now):
        return (
            job.get('state') == 'quarantined'
            and job.get('quarantine_reason') == 'worker_failed'
            and (
                job.get('recovery_state') == 'failed_held'
                or RecoveryPolicy.from_dict(
                    (job.get('policy_parts') or {}).get('recovery', {})
                ).terminal_empty_disposition
                and spent_canary(job)
            )
            and bool(job.get('recovery', {}).get('settled_at'))
            and not job.get('token')
            and job.get('lease_until', 0) <= now
            and job.get('merge_pending') is False
            and not job.get('result')
            and not existing
            and not job.get('silence_disposition')
        )

    def prepare(
        self, segment_id, owner_id, plan_digest, expected_recovery, now, *, gpu_padded_retry_empty=False, silent=False
    ):
        candidates, observations = {}, []
        token = uuid4().hex

        def commit(tx):
            observations.clear()
            job, binding = self.checked(tx, segment_id)
            policy = stage_in_transaction(
                tx, job, 'recovery', candidates=candidates, observations=observations, server_flags=self.server_flags
            )
            if not policy.speech_empty_multilingual or not policy.recovery_enabled:
                raise ProjectionBlocked('speech redrive disabled')
            existing = tx.get('results', segment_id)
            marker = job.get('speech_redrive') or {}
            if (
                binding.owner_id != owner_id
                or job.get('recovery') != expected_recovery
                or expected_recovery.get('epoch') != 1
                or not expected_recovery.get('started_at')
                or not expected_recovery.get('settled_at')
            ):
                raise ProjectionBlocked('speech redrive ownership changed')
            if marker:
                if (
                    marker.get('plan_digest') != plan_digest
                    or marker.get('paid_epoch') != PAID_EPOCH
                    or marker.get('privacy_generation') != binding.privacy_generation
                    or marker.get('provider') != 'modulate'
                    or marker.get('silent', False) is not silent
                ):
                    raise ProjectionBlocked('different speech redrive intent')
                return job
            if not self.terminal(job, existing, now):
                raise ProjectionBlocked('terminal held obligation required')
            if gpu_padded_retry_empty and padded_skipped(job):
                raise ProjectionBlocked('padded retry was skipped')
            job['speech_redrive'] = {
                'gpu_padded_retry_empty': gpu_padded_retry_empty,
                'silent': silent,
                'paid_epoch': PAID_EPOCH,
                'token': token,
                'plan_digest': plan_digest,
                'state': 'prepared',
                'provider': 'modulate',
                'prepared_at': now,
                'privacy_generation': binding.privacy_generation,
                'prior_recovery': deepcopy(expected_recovery),
            }
            tx.put('jobs', segment_id, job)
            return job

        result = self.store.run(commit)
        record_policy_observations(observations)
        return result

    def start(self, segment_id, token, plan_digest, now):
        _, policy = load_stage_policy(self.store, segment_id, 'recovery', server_flags=self.server_flags)
        if policy is None or not policy.speech_empty_multilingual:
            return False

        def commit(tx):
            job, binding = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            marker = job.get('speech_redrive') or {}
            if (
                not policy.recovery_enabled
                or not self.terminal(job, existing, now)
                or marker.get('token') != token
                or marker.get('plan_digest') != plan_digest
                or marker.get('paid_epoch') != PAID_EPOCH
                or marker.get('provider') != 'modulate'
                or marker.get('privacy_generation') != binding.privacy_generation
                or marker.get('state') != 'prepared'
                or marker.get('prior_recovery') != job.get('recovery')
            ):
                return False
            marker.update(state='running', started_at=now)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def settle(self, segment_id, token, plan_digest, now, result_uri=None, *, failure=None, outcome="success"):
        def commit(tx):
            job, binding = self.checked(tx, segment_id)
            existing = tx.get('results', segment_id)
            marker = job.get('speech_redrive') or {}
            if (
                marker.get('token') != token
                or marker.get('plan_digest') != plan_digest
                or marker.get('paid_epoch') != PAID_EPOCH
                or marker.get('provider') != 'modulate'
                or marker.get('privacy_generation') != binding.privacy_generation
                or marker.get('prior_recovery') != job.get('recovery')
            ):
                return False
            if marker.get('state') == 'completed':
                return isinstance(result_uri, str) and job.get('result') == asdict(
                    WorkResult(segment_id, result_uri, outcome)
                )
            if marker.get('state') != 'running' or not self.terminal(job, existing, now):
                return False
            if outcome not in {'success', 'no_recoverable_speech'}:
                raise ValueError('closed speech outcome required')
            if result_uri:
                owner = tx.get('owners', owner_key(job['owner_id']))
                owner['revision'] = owner.get('revision', 0) + 1
                marker.update(state='completed', settled_at=now)
                job.update(
                    state='result_ready',
                    ready_at=now,
                    merge_pending=True,
                    recovery_state='recovered',
                    result=asdict(WorkResult(segment_id, result_uri, outcome)),
                )
                tx.put('owners', owner_key(job['owner_id']), owner)
            else:
                if not failure or failure.get('stage') not in STAGES or failure.get('reason') not in REASONS:
                    raise ValueError('closed redrive failure required')
                marker.update(state='failed_held', settled_at=now, failure=dict(failure))
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)
