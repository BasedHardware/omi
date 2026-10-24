"""Bounded owner-only repair of committed results; planning never resolves policy."""

from collections import Counter
import hashlib
import json

from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_policy import UnpinnedPolicyRefused
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.scheduler import owner_key

OPERATION = 'batch-projection-repair-v1'
ACTIVE = {'pending', 'persisted', 'ready'}


def plan_owner(store, owner_id: str, *, max_units: int = 1000, lookback_units: int = 100) -> dict:
    if not owner_id or '/' in owner_id or not 1 <= max_units <= 5000 or not 0 <= lookback_units <= 1000:
        raise ValueError('invalid owner repair scope or budget')
    key = owner_key(owner_id)
    owner = store.client.collection(f'{store.namespace}_owners').document(key).get().to_dict() or {}
    watermark = owner.get('projection_watermark')
    rows = {}
    snapshots = []
    seen = set()

    def read(sid):
        if sid in seen:
            raise ProjectionBlocked('owner repair chain cycle')
        seen.add(sid)
        row = store.client.collection(f'{store.namespace}_results').document(sid).get().to_dict()
        if row is None:
            # Absent (for example retention-expired) history is reported by the
            # caller; an existing foreign or relabeled row still refuses below.
            return None
        if row.get('owner_key') != key or row.get('segment_id') != sid:
            raise ProjectionBlocked('owner repair result scope mismatch')
        snapshots.append((sid, row.get('result'), row.get('committed_at')))
        rows[sid] = row
        return row

    # Lost replies/follow-up crashes may leave obligations behind the watermark.
    # Backward discovery stops at the first missing historical receipt (completed
    # results legitimately expire) and reports it; forward discovery still runs
    # from the watermark id. Budget exhaustion is reported separately.
    before = []
    previous = watermark
    lookback_missing = False
    lookback_truncated = False
    for _ in range(lookback_units):
        if previous is None:
            break
        row = read(previous)
        if row is None:
            lookback_missing = True
            break
        before.append(previous)
        previous = row.get('previous_segment_id')
    else:
        lookback_truncated = previous is not None
    after = []
    previous = watermark
    for _ in range(max_units):
        sid = store.projection_successor(key, previous)
        if sid is None:
            break
        if read(sid) is None:
            raise ProjectionBlocked('owner repair forward result missing')
        after.append(sid)
        previous = sid
    forward_truncated = len(after) == max_units and store.projection_successor(key, previous) is not None
    ordered = list(reversed(before)) + after
    units = [sid for sid in ordered if rows[sid].get('projection_state') in ACTIVE]
    unpinned = 0
    for sid in units:
        job = store.client.collection(f'{store.namespace}_jobs').document(sid).get().to_dict() or {}
        if job.get('owner_id') != owner_id:
            raise ProjectionBlocked('owner repair job scope mismatch')
        policy = (job.get('policy_parts') or {}).get('projection')
        unpinned += policy is None
        snapshots.append((sid, job.get('projection_binding'), policy))
    digest = hashlib.sha256(
        json.dumps([OPERATION, store.namespace, owner_id, watermark, snapshots], sort_keys=True).encode()
    ).hexdigest()
    return {
        'operation': OPERATION,
        'plan_sha256': digest,
        'units': units,
        'unpinned_units': unpinned,
        'states': dict(Counter(row.get('projection_state', 'unknown') for row in rows.values())),
        'lookback_truncated': lookback_truncated,
        'lookback_missing': lookback_missing,
        'forward_truncated': forward_truncated,
    }


def apply_owner(projector, plan: dict) -> dict:
    counts = Counter()
    if plan.get('unpinned_units'):
        raise UnpinnedPolicyRefused('projection')
    for sid in plan['units']:
        # Ordinary assignment and completion own all CAS/privacy/replay fences.
        # No merge, provider, scheduler, paid intent, or manual watermark writes.
        try:
            job = projector.store.ref('jobs', sid).get().to_dict() or {}
            if (job.get('policy_parts') or {}).get('projection') is None:
                raise UnpinnedPolicyRefused('projection')
            projector.project(sid)
        except (ProjectionBlocked, BatchPrivacyBlocked):
            counts['blocked'] += 1
            break
        row = projector.store.ref('results', sid).get().to_dict() or {}
        counts[row.get('projection_state', 'unknown')] += 1
    return dict(counts)
