"""Bounded source-result ownership joined to admission and assignment transactions.

Receipts contain no text or raw digests. They never authorize a covered ACK or
WAL release. An alias owns a fresh audio artifact and a protocol-fenced result
marker; only a fenced canonical-loss transition can admit its own audio again.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from config.batch_pipeline import FRESH_CAPTURE_LAG_SECONDS
from database.batch_pipeline_staging import artifact_id, retire_upload_reservation
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from utils.batch_pipeline.retention import RECEIPT_RETENTION
from utils.batch_pipeline.result_protocol import stamp
from utils.batch_pipeline.contracts import WorkItem, WorkResult
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline import source_reuse

# Reuse the existing projection-receipt collection's TTL and erasure owner.
TABLE = 'projections'


def receipt_id(key):
    return f'source-{key}'


class SourceReuseUnavailable(ProjectionBlocked):
    """A recorded dependency must wait for reuse or its durable paid fallback."""


def dependencies(job, receipt=None):
    binding = job.get('projection_binding') or {}
    return sorted(
        {
            value
            for value in (
                job.get('conversation_id'),
                job.get('capture_source_conversation_id'),
                binding.get('target_conversation_id'),
                *((receipt or {}).get('source_conversation_ids') or []),
                *((receipt or {}).get('conversation_ids') or []),
                *((job.get('source_conversation_ids')) or []),
            )
            if value
        }
    )


def current(tx, item: WorkItem, now: float, *, expected=None, require_artifacts=True) -> dict[str, Any] | None:
    """Fresh transactional source, generation, deletion, result and accounting proof."""
    key = item.source_reuse_key
    row = tx.get(TABLE, receipt_id(key)) if key else {}
    stamp = datetime.fromtimestamp(now, timezone.utc)
    if (
        not row
        or row.get('segment_id') == item.segment_id
        or row.get('owner_id') != item.owner_id
        or row.get('privacy_generation') != item.privacy_generation
        or not isinstance(row.get('expires_at'), datetime)
        or row['expires_at'] <= stamp
        or (expected is not None and row.get('segment_id') != expected)
    ):
        return None
    sid = row['segment_id']
    job = tx.get('jobs', sid)
    entry = tx.get('results', sid)
    binding = job.get('projection_binding') or {}
    ledger = tx.get('content', f"{item.owner_id}/{binding.get('content_id', '')}") if binding.get('content_id') else {}
    receipt = entry.get('projection') or {}
    if (
        job.get('owner_id') != item.owner_id
        or job.get('privacy_generation') != item.privacy_generation
        or job.get('source_reuse_key') != key
        or job.get('source_alias')
        or binding.get('owner_id') != item.owner_id
        or not row.get('complete')
        or job.get('duration_seconds') != item.duration_seconds
        or job.get('capture_at') != item.capture_at
        or job.get('state') != 'committed'
        or entry.get('result') != job.get('result')
        or entry.get('projection_state') == 'erased'
        or receipt.get('state') != 'ready'
        or receipt.get('disposition')
        or receipt.get('privacy_reason')
        or any(
            p.get('state') != 'ready' or p.get('disposition') or p.get('privacy_reason')
            for p in (entry.get('projection_parts') or {}).values()
        )
        or ledger.get('status') != 'completed'
        or ledger.get('job_id') != binding.get('job_id')
        or (job.get('result') or {}).get('outcome') not in {'success', 'silence'}
    ):
        return None
    if require_artifacts:
        for uri in (job.get('audio_uri'), (job.get('result') or {}).get('result_uri')):
            if not uri:
                return None
            artifact = tx.get('artifacts', artifact_id(sid, uri))
            if (
                artifact.get('owner_id') != item.owner_id
                or artifact.get('privacy_generation') != item.privacy_generation
                or isinstance(artifact.get('cleanup_after'), datetime)
                and artifact['cleanup_after'] <= stamp
                or artifact.get('erasure_requested')
                or artifact.get('write_pending_until')
            ):
                return None
    ids = sorted(set(dependencies(job, row)) | set(dependencies(asdict(item))))
    tx.check_privacy(item.owner_id, ids, item.privacy_generation)
    return {'segment_id': sid, 'job': job, 'receipt': receipt, 'dependencies': ids}


def lookup(store, item, now):
    if not source_reuse.enabled() or not item.source_reuse_key:
        return None
    return store.run(lambda tx: current(tx, item, now))


def enqueue_alias(tx, item, now, *, policy, proposal):
    canonical = current(tx, item, now, expected=proposal['segment_id'])
    if not source_reuse.enabled() or canonical is None:
        raise SourceReuseUnavailable('source alias changed before admission')
    if item.source_alias_of != canonical['segment_id']:
        raise SourceReuseUnavailable('source alias marker binding changed')
    if tx.get('jobs', item.segment_id):
        raise SourceReuseUnavailable('source alias admission already owned')
    # Outside both paid queues. OrderedMerge already consumes result_ready work.
    key = owner_key(item.owner_id)
    owner = tx.get('owners', key)
    job = {
        **item.to_dict(),
        'priority': int(item.priority),
        'owner_key': key,
        'policy': policy.to_dict(),
        'policy_source': 'admission',
        'source_alias': {'segment_id': canonical['segment_id']},
        'source_conversation_ids': canonical['dependencies'],
        'state': 'result_ready',
        'attempt': 0,
        'token': '',
        'lease_until': 0.0,
        'available_at': now,
        'enqueued_at': now,
        'ready_at': now,
        'merge_pending': True,
        'fresh_capture': now - item.capture_at - item.duration_seconds <= FRESH_CAPTURE_LAG_SECONDS,
        'result': WorkResult(item.segment_id, proposal['result_uri']).to_dict(),
    }
    stamp(job, 'source_alias_version')
    tx.put('jobs', item.segment_id, job)
    owner['revision'] = owner.get('revision', 0) + 1
    tx.put('owners', key, owner)
    return True


def prepare(session, transaction):
    """Read the single-owner fence before assignment writes, also on old accepted jobs after OFF."""
    session.source_owner = {}
    key = session.job.get('source_reuse_key')
    if not key:
        return
    ref = session.store.ref(TABLE, receipt_id(key))
    row = ref.get(transaction=transaction).to_dict() or {}
    session.source_owner = row
    if (
        row
        and not session.receipt()
        and (
            row.get('owner_id') != session.binding.owner_id
            or row.get('privacy_generation') != session.binding.privacy_generation
        )
    ):
        raise SourceReuseUnavailable('source owner generation changed')
    if session.receipt():
        return
    if row and row.get('segment_id') != session.segment_id and not getattr(session, 'allow_source_alias', False):
        source_reuse.observe('duplicate_projection_refusal')
        raise SourceReuseUnavailable('source range already has a projection owner')


def claim(session, transaction, receipt):
    key = session.job.get('source_reuse_key')
    if not key or getattr(session, 'allow_source_alias', False) or receipt.get('disposition'):
        return
    # Every marked job is fenced even when new alias admission is killed.
    row = getattr(session, 'source_owner', {})
    if row and row.get('segment_id') != session.segment_id:
        raise SourceReuseUnavailable('source range already has a projection owner')
    ids = sorted(
        set(dependencies(session.job))
        | set(row.get('source_conversation_ids') or [])
        | {value for value in [receipt.get('conversation_id')] if value}
        | {r['conversation_id'] for r in receipt.get('size_rollover_outputs', [])}
    )
    if len(ids) > 256:
        raise SourceReuseUnavailable('source dependency bound exceeded')
    transaction.set(
        session.store.ref(TABLE, receipt_id(key)),
        {
            'owner_id': session.binding.owner_id,
            'owner_key': owner_key(session.binding.owner_id),
            'segment_id': session.segment_id,
            'privacy_generation': session.binding.privacy_generation,
            'source_conversation_ids': ids,
            # Only the whole unit's ready summary may license an admission alias.
            'complete': receipt.get('state') == 'ready',
            **(
                {'fallback_from': session.job['source_alias_fallback']['source_segment_id']}
                if session.job.get('source_alias_fallback')
                else {}
            ),
            'expires_at': datetime.fromtimestamp(session.now, timezone.utc) + RECEIPT_RETENTION,
        },
    )


def attach_alias_artifacts(tx, item, proposal):
    """Keep every own artifact discoverable from canonical source/output erasure."""
    job = tx.get('jobs', item.segment_id)
    for uri in (item.audio_uri, proposal['result_uri']):
        key = artifact_id(item.segment_id, uri)
        artifact = tx.get('artifacts', key)
        if (
            not artifact
            or artifact.get('owner_id') != item.owner_id
            or artifact.get('privacy_generation') != item.privacy_generation
            or artifact.get('erasure_requested')
        ):
            raise SourceReuseUnavailable('source alias artifact reservation unavailable')
        artifact['source_conversation_ids'] = job['source_conversation_ids']
        retire_upload_reservation(artifact)
        tx.put('artifacts', key, artifact)
