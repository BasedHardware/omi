"""Persist a unit's first fallback through a canonical sibling fence."""

import logging
from dataclasses import replace
from typing import Any, Literal, overload
from collections.abc import Iterable

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
    raw = job.get('policy')
    if raw is not None and not isinstance(raw, dict):
        raise ValueError('serialized batch policy must be a dict')
    return raw


def policy_in_transaction(tx, job: dict, *, observations=None, candidates=None) -> BatchUnitPolicy:
    raw = recorded_policy(job)
    if raw is not None:
        policy = BatchUnitPolicy.from_dict(raw)
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
            lambda: admission_fallback(job),
        )
    )
    if observations is not None:
        observations.append(('policy_fallback', policy.policy_id))
    for sibling in ([job] if raw is not None or anchor['segment_id'] == job['segment_id'] else [anchor, job]):
        sibling['policy'] = policy.to_dict()
        sibling['policy_source'] = 'fallback'
        tx.put('jobs', sibling['segment_id'], sibling)
    # The row is the durable event receipt. Emit outside the retriable callback
    # via load_job_policy; transactional stage callers also retain policy_source.
    return policy


def admission_fallback(job):
    """Called only by an admitting role, never a scheduler/projection role."""
    policy = resolve_batch_policy(job['owner_id'], source='fallback')
    if job.get('state') == 'record_pending':
        # Pre-E1 main's live-owner reservation already accepted this capture.
        policy = replace(policy, batch_enabled=True, live_admission_enabled=True, live_record_enabled=True)
    return policy


def candidate_once(candidates, key, resolve):
    if candidates is None:
        return resolve()
    if key not in candidates:
        candidates[key] = resolve()
    return candidates[key]


def check_unit_privacy(tx, job):
    binding = job.get('projection_binding') or {}
    ids: set[str] = set(job.get('conversation_ids') or ())
    ids.update(value for value in (job.get('conversation_id'), binding.get('target_conversation_id')) if value)
    if binding and 'capture_at' in job:
        from utils.sync.capture import chunk_identity

        ids.add(
            chunk_identity(
                job['owner_id'],
                binding.get('source', 'omi'),
                binding.get('client_device_id'),
                binding.get('is_locked', False),
                job['capture_at'],
            )
        )
    tx.check_privacy(job['owner_id'], ids, job.get('privacy_generation', binding.get('privacy_generation')))


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
                    check_unit_privacy(tx, candidate)
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
    raw = (job.get('policy_parts') or {}).get(stage)
    cls = STAGE_TYPES[stage]
    if raw is not None:
        if not isinstance(raw, dict):
            raise ValueError('serialized stage policy must be a dict')
        return cls.from_dict(raw)
    check_unit_privacy(tx, job)
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
        if recorded_policy(sibling) is None:
            sibling['policy_part_sources'] = {**(sibling.get('policy_part_sources') or {}), stage: 'fallback'}
        tx.put('jobs', sibling['segment_id'], sibling)
    if observations is not None:
        observations.append(('policy_fallback' if recorded_policy(job) is None else 'policy_stage', policy.policy_id))
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
    record_policy_observations(observations)
    return job, policy


def record_policy_observations(observations: Iterable[tuple[str, Any]]) -> None:
    from config.policy.telemetry import record_policy_source

    for event, policy_id in observations:
        if event in {'policy_fallback', 'policy_stage'}:
            record_policy_source('fallback' if event == 'policy_fallback' else 'stage', policy_id)


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
