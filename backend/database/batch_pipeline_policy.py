"""Persist a unit's first fallback through a canonical sibling fence."""

import logging

from config.policy import BatchUnitPolicy, resolve_batch_policy
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


def policy_in_transaction(tx, job: dict, *, observations=None) -> BatchUnitPolicy:
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
    raw = recorded_policy(anchor)
    policy = (
        BatchUnitPolicy.from_dict(raw) if raw is not None else resolve_batch_policy(job['owner_id'], source='fallback')
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


def load_job_policy(store, segment_id: str):
    def commit(tx):
        job = tx.get('jobs', segment_id)
        if not job:
            return job, None, False
        missing = recorded_policy(job) is None
        policy = policy_in_transaction(tx, job)
        return job, policy, missing

    job, policy, fallback = store.run(commit)
    if fallback:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='sync_dispatch', from_mode='none', to_mode='batch', reason='other', outcome='recovered'
        )
        from config.policy.telemetry import record_policy_source

        record_policy_source('fallback', policy.policy_id)
    return job, policy
