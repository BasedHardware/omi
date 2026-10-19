"""Persist a unit's first fallback through a canonical sibling fence."""

import logging
from typing import Literal, overload

from config.policy import (
    BatchUnitPolicy,
    ProjectionPolicy,
    SchedulerPolicy,
    RecoveryPolicy,
    FirstSummaryPolicy,
    resolve_batch_policy,
    resolve_stage_policy,
)
from config.policy.stages import STAGE_TYPES
from config.policy.parts import PolicyPart
from database.batch_pipeline_privacy import BatchPrivacyBlocked

logger = logging.getLogger(__name__)


def recorded_policy(job: dict) -> dict | None:
    binding = job.get('projection_binding') or {}
    raw = binding.get('policy')
    if raw is None:
        raw = job.get('policy')
    if raw is not None and not isinstance(raw, dict):
        raise ValueError('serialized batch policy must be a dict')
    return raw


def policy_in_transaction(tx, job: dict, *, observations=None, candidates=None) -> BatchUnitPolicy:
    binding = job.get('projection_binding') or {}
    raw = recorded_policy(job)
    if raw is not None:
        policy = BatchUnitPolicy.from_dict(raw)
        if binding and binding.get('policy') is None:
            job['projection_binding'] = {**binding, 'policy': policy.to_dict()}
            tx.put('jobs', job['segment_id'], job)
        return policy
    # All siblings serialize through the first extant sibling. Do not rewrite
    # 128 siblings per queue visited: a pull can visit 128 owners and must stay
    # below Firestore's 450 buffered-write budget. Each old reader copies the
    # canonical snapshot to its own row before using it.
    anchor = unit_anchor(tx, job)
    raw = recorded_policy(anchor)
    policy = (
        BatchUnitPolicy.from_dict(raw)
        if raw is not None
        else candidate_once(
            candidates,
            (anchor['segment_id'], 'admission'),
            lambda: resolve_batch_policy(job['owner_id'], source='fallback'),
        )
    )
    if observations is not None:
        observations.append(('policy_fallback', policy.policy_id))
    for sibling in ([job] if raw is not None or anchor['segment_id'] == job['segment_id'] else [anchor, job]):
        sibling['policy'] = policy.to_dict()
        sibling['policy_source'] = 'fallback'
        if sibling.get('projection_binding'):
            sibling['projection_binding'] = {**sibling['projection_binding'], 'policy': policy.to_dict()}
        tx.put('jobs', sibling['segment_id'], sibling)
    # The row is the durable event receipt. Emit outside the retriable callback
    # via load_job_policy; transactional stage callers also retain policy_source.
    return policy


def candidate_once(candidates, key, resolve):
    if candidates is None:
        return resolve()
    if key not in candidates:
        candidates[key] = resolve()
    return candidates[key]


def unit_anchor(tx, job):
    binding = job.get('projection_binding') or {}
    anchor = job
    for sid in binding.get('segment_ids', ()):
        candidate = job if sid == job['segment_id'] else tx.get('jobs', sid)
        if candidate:
            if candidate.get('owner_id') != job['owner_id']:
                raise ValueError('policy sibling owner mismatch')
            if candidate['segment_id'] != job['segment_id']:
                try:
                    tx.check_privacy(
                        candidate['owner_id'],
                        (candidate['conversation_id'],) if candidate.get('conversation_id') else (),
                        candidate.get('privacy_generation'),
                    )
                except BatchPrivacyBlocked:
                    continue
            anchor = candidate
            break
    return anchor


@overload
def stage_in_transaction(
    tx, job, stage: Literal['projection'], *, observations=None, candidates=None
) -> ProjectionPolicy: ...


@overload
def stage_in_transaction(
    tx, job, stage: Literal['scheduler'], *, observations=None, candidates=None
) -> SchedulerPolicy: ...


@overload
def stage_in_transaction(
    tx, job, stage: Literal['recovery'], *, observations=None, candidates=None
) -> RecoveryPolicy: ...


@overload
def stage_in_transaction(
    tx, job, stage: Literal['first_summary'], *, observations=None, candidates=None
) -> FirstSummaryPolicy: ...


@overload
def stage_in_transaction(tx, job, stage: str, *, observations=None, candidates=None) -> PolicyPart: ...


def stage_in_transaction(tx, job, stage, *, observations=None, candidates=None):
    """CAS one owner part, serializing sibling segments through the same anchor.

    An absent part is expected on new work. No other role's values are filled
    here. Once present, even a partial dict uses code defaults without env.
    """
    policy_in_transaction(tx, job, observations=observations, candidates=candidates)
    raw = (job.get('policy_parts') or {}).get(stage)
    cls = STAGE_TYPES[stage]
    if raw is not None:
        if not isinstance(raw, dict):
            raise ValueError('serialized stage policy must be a dict')
        return cls.from_dict(raw)
    anchor = unit_anchor(tx, job)
    raw = (anchor.get('policy_parts') or {}).get(stage)
    policy = (
        cls.from_dict(raw)
        if raw is not None
        else candidate_once(
            candidates, (anchor['segment_id'], stage), lambda: resolve_stage_policy(job['owner_id'], stage)
        )
    )
    for sibling in ([job] if raw is not None or anchor['segment_id'] == job['segment_id'] else [anchor, job]):
        # Copy only this part; retain every concurrent/previous owner's receipt.
        sibling['policy_parts'] = {**(sibling.get('policy_parts') or {}), stage: policy.to_dict()}
        tx.put('jobs', sibling['segment_id'], sibling)
    if observations is not None:
        observations.append(('policy_stage', policy.policy_id))
    return policy


def load_stage_policy(store, segment_id, stage):
    observations = []
    candidates = {}

    def commit(tx):
        observations.clear()  # Retried callbacks publish only the committed attempt.
        job = tx.get('jobs', segment_id)
        if not job:
            return job, None
        policy = stage_in_transaction(tx, job, stage, observations=observations, candidates=candidates)
        return job, policy

    job, policy = store.run(commit)
    from config.policy.telemetry import record_policy_source

    for event, policy_id in observations:
        record_policy_source('fallback' if event == 'policy_fallback' else 'stage', policy_id)
    return job, policy


def load_job_policy(store, segment_id: str):
    candidates = {}

    def commit(tx):
        job = tx.get('jobs', segment_id)
        if not job:
            return job, None, False
        missing = recorded_policy(job) is None
        policy = policy_in_transaction(tx, job, candidates=candidates)
        return job, policy, missing

    job, policy, fallback = store.run(commit)
    if fallback:
        from config.policy.telemetry import record_policy_source

        record_policy_source('fallback', policy.policy_id)
    return job, policy
