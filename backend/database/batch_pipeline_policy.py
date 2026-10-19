"""Persist historical-row fallback once, atomically across sibling bindings."""

import logging

from config.policy import BatchUnitPolicy, resolve_batch_policy

logger = logging.getLogger(__name__)


def policy_in_transaction(tx, job: dict, *, observations=None) -> BatchUnitPolicy:
    binding = job.get('projection_binding') or {}
    raw = binding.get('policy') or job.get('policy')
    if raw:
        return BatchUnitPolicy.from_dict(raw)
    # All siblings serialize through the first extant sibling. Do not rewrite
    # 128 siblings per queue visited: a pull can visit 128 owners and must stay
    # below Firestore's 450 buffered-write budget. Each old reader copies the
    # canonical snapshot to its own row before using it.
    anchor = job
    for sid in binding.get('segment_ids', ()):
        candidate = job if sid == job['segment_id'] else tx.get('jobs', sid)
        if candidate:
            anchor = candidate
            break
    raw = (anchor.get('projection_binding') or {}).get('policy') or anchor.get('policy')
    policy = BatchUnitPolicy.from_dict(raw) if raw else resolve_batch_policy(job['owner_id'], source='fallback')
    if observations is not None:
        observations.append(('policy_fallback', policy.policy_id))
    for sibling in ([job] if raw or anchor['segment_id'] == job['segment_id'] else [anchor, job]):
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
        missing = not ((job.get('projection_binding') or {}).get('policy') or job.get('policy'))
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
