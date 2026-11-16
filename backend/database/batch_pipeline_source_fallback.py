"""Reprocess an unresolved alias's own audio, preserving its original log slot.

Only a transaction that proved canonical reuse unavailable may detach inherited
canonical dependencies. Own upload/privacy fences and normal paid admission stay.
"""

from dataclasses import replace
from datetime import datetime, timezone

from config.policy import BatchUnitPolicy
from database.batch_pipeline_staging import artifact_id
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_policy import check_unit_privacy
from database.sync_ledger_ownership import batch_projection_ledger_owner_matches
from utils.batch_pipeline.retention import RECEIPT_RETENTION
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.capture import chunk_identity


def enqueue(session, view, item, now):
    from database.batch_pipeline_source_reuse import TABLE, receipt_id

    job, entry = dict(session.job), dict(session.entry)
    if (
        not job.get('source_alias')
        or job.get('state') != 'committed'
        or entry.get('projection_state') == 'erased'
        or session.ledger.get('status') not in {'processing', 'partial'}
        or (entry.get('projection') or {}).get('disposition') not in {None, 'source_alias'}
    ):
        raise ProjectionBlocked('unresolved retained alias required for fallback')
    check_unit_privacy(view, job)
    binding = job['projection_binding']
    own_ids = sorted(
        {
            value
            for value in (
                job.get('conversation_id'),
                job.get('capture_source_conversation_id'),
                binding.get('target_conversation_id'),
                chunk_identity(
                    item.owner_id,
                    binding.get('source', 'omi'),
                    binding.get('client_device_id'),
                    binding.get('is_locked', False),
                    item.capture_at,
                ),
            )
            if value
        }
    )
    reservations = []
    for uri in (job['audio_uri'], job['result']['result_uri']):
        key = artifact_id(item.segment_id, uri)
        artifact = view.get('artifacts', key)
        if uri == job['audio_uri'] and (
            artifact.get('owner_id') != item.owner_id
            or artifact.get('privacy_generation') != item.privacy_generation
            or artifact.get('erasure_requested')
            or artifact.get('write_pending_until')
            or isinstance(artifact.get('cleanup_after'), datetime)
            and artifact['cleanup_after'] <= datetime.fromtimestamp(now, timezone.utc)
        ):
            raise ProjectionBlocked('retained alias artifact required for fallback')
        if artifact.get('owner_id') == item.owner_id and artifact.get('privacy_generation') == item.privacy_generation:
            reservations.append((key, artifact))
    owner = view.get('owners', owner_key(item.owner_id))
    for name in ('projection', 'projection_parts', 'source_conversation_ids', 'source_alias_version'):
        entry.pop(name, None)
    marker = {
        'source_segment_id': job['source_alias']['segment_id'],
        'started_at': now,
        'prior_dependencies': job.get('source_conversation_ids') or [],
        'log_slot': entry,
    }
    # Aliases skipped LID. The ordinary multilingual provider stage performs
    # fresh funding admission and can transcribe long audio without inventing
    # a frozen supported-language verdict or relying on bounded GPU recovery.
    if not isinstance(job.get('policy'), dict):
        raise ProjectionBlocked('recorded alias funding policy required')
    policy = BatchUnitPolicy.from_dict(job['policy'])
    reason = 'byok' if policy.provider_reason == 'byok' else 'unsupported_language'
    policy = replace(policy, stt_route='provider', provider_reason=reason, provider_service='modulate')
    # Nothing is copied from the canonical transcript. The independent upload
    # keeps its own conversation/chunk/generation fences; inherited references
    # remain audit provenance, not authority to restore a deleted destination.
    job.update(
        source_alias_fallback=marker,
        source_conversation_ids=own_ids,
        requires_compute_admission=False,
        protocol_version=2,
        source_reuse_version=1,
        state='provider_pending',
        stt_route={
            'stt_route': 'provider',
            'provider_reason': reason,
            'provider_service': 'modulate',
            'language': 'multi',
        },
        policy=policy.to_dict(),
        attempt=0,
        token='',
        lease_until=0.0,
        available_at=now,
        merge_pending=True,
    )
    for name in ('source_alias', 'source_alias_of', 'source_alias_version', 'result', 'ready_at', 'conversation_ids'):
        job.pop(name, None)
    for key, artifact in reservations:
        artifact['source_conversation_ids'] = own_ids
        artifact['conversation_ids'] = own_ids
        view.put('artifacts', key, artifact)
    view.put('jobs', item.segment_id, job)
    # Reserve the range before paid work. Recovery of the old canonical cannot
    # steal it back, and other aliases wait for this single fallback owner.
    view.put(
        TABLE,
        receipt_id(item.source_reuse_key),
        {
            'owner_id': item.owner_id,
            'owner_key': owner_key(item.owner_id),
            'segment_id': item.segment_id,
            'privacy_generation': item.privacy_generation,
            'source_conversation_ids': own_ids,
            'complete': False,
            'fallback_from': marker['source_segment_id'],
            'expires_at': datetime.fromtimestamp(now, timezone.utc) + RECEIPT_RETENTION,
        },
    )
    owner['revision'] = owner.get('revision', 0) + 1
    view.put('owners', owner_key(item.owner_id), owner)
    view.flush()
    # The dormant slot lives on the job while ordinary worker/provider recovery
    # expects no committed result. Both changes commit atomically.
    view.transaction.delete(session.result_ref)


def merge_ready(tx, job, now):
    """Replace only the unresolved marker; never append a second owner-log slot."""
    existing = tx.get('results', job['segment_id'])
    entry = dict((job.get('source_alias_fallback') or {}).get('log_slot') or {})
    binding = job.get('projection_binding') or {}
    ledger = tx.get('content', f"{job['owner_id']}/{binding.get('content_id', '')}")
    check_unit_privacy(tx, job)
    if (
        existing
        or entry.get('segment_id') != job['segment_id']
        or entry.get('owner_key') != job['owner_key']
        or entry.get('projection_state') == 'erased'
        or entry.get('projection')
        or job.get('state') != 'result_ready'
        or ledger.get('status') not in {'processing', 'partial'}
        or not batch_projection_ledger_owner_matches(
            ledger, binding['job_id'], binding.get('run_token'), binding.get('run_epoch')
        )
    ):
        raise ProjectionBlocked('fallback result binding changed')
    owner = tx.get('owners', job['owner_key'])
    entry.update(
        result=job['result'],
        protocol_version=2,
        source_reuse_version=1,
        projection_redriven_at=now,
        projection_state='pending',
    )
    entry.pop('source_alias_version', None)
    job.update(state='committed', merge_pending=False)
    owner['revision'] = owner.get('revision', 0) + 1
    tx.put('results', job['segment_id'], entry)
    tx.put('jobs', job['segment_id'], job)
    tx.put('owners', job['owner_key'], owner)
    return entry
