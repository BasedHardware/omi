"""Authenticated intake provenance projected with existing sync policies."""

from dataclasses import dataclass
import math
import os
from typing import Any

from database.batch_pipeline_projection import ProjectionBlocked
from models.geolocation import Geolocation
from utils.batch_pipeline.contracts import WorkItem, ProjectionBinding


@dataclass(frozen=True)
class ResolvedContext:
    target_id: str | None
    binding_reason: str | None = None
    geolocation: Geolocation | None = None


def resolve_context(
    item: WorkItem,
    binding: ProjectionBinding,
    context: dict[str, Any],
    client: Any,
    *,
    projection_item: WorkItem | None = None,
) -> ResolvedContext:
    expected = {
        'owner_id': item.owner_id,
        'job_id': binding.job_id,
        'content_id': binding.content_id,
        'segment_id': item.segment_id,
        'capture_at': item.capture_at,
        'source': binding.source,
        'should_lock': binding.is_locked,
        'client_device_id': binding.client_device_id,
        'client_platform': binding.client_platform,
        'conversation_id': binding.target_conversation_id,
    }
    if any(context.get(key) != value for key, value in expected.items()):
        raise ProjectionBlocked('authenticated intake metadata binding mismatch')
    geo = context.get('geolocation')
    if geo is not None:
        from utils.conversations.location import resolve_geolocation

        geo = resolve_geolocation(Geolocation.model_validate(geo))
    if binding.record_origin:
        return ResolvedContext(binding.target_conversation_id, geolocation=geo)
    projection_item = projection_item or item
    target = binding.target_conversation_id
    origin = context.get('recording_session_id')
    start, end = context.get('audio_start_seconds'), context.get('audio_end_seconds')
    for value in (start, end):
        if value is not None and (type(value) not in (float, int) or not math.isfinite(value)):
            raise ProjectionBlocked('invalid intake recording clock')
    if origin is not None and (not isinstance(origin, str) or not origin or len(origin) > 256):
        raise ProjectionBlocked('invalid intake recording identity')
    if start is not None and end is not None and start > end:
        raise ProjectionBlocked('invalid intake recording interval')
    from utils.sync.recording_lineage import (
        lineage_resolution_requested,
        plan_segment_targets,
        ambiguous_binding_pending,
    )

    # These are the authenticated upload names frozen by accept_batch_upload,
    # not optional consent-dependent (and potentially digest-named) archives.
    # Only pre-deploy contexts lacking the field retain the old archive check.
    filenames = (
        context.get('filenames') or []
        if 'filenames' in context
        else [os.path.basename(path) for path in context.get('raw_capture_paths') or []]
    )
    if not isinstance(filenames, list) or any(not isinstance(name, str) for name in filenames):
        raise ProjectionBlocked('invalid intake upload filenames')
    requested = lineage_resolution_requested(
        item.owner_id,
        origin,
        start,
        end,
        job_id=binding.job_id,
        capture_evidence_claims=context.get('capture_evidence_claims'),
        filenames=filenames,
        stage='batch_projection',
    )
    reason = None
    if requested:
        if not isinstance(origin, str):
            raise ProjectionBlocked('recording identity required for lineage resolution')
        reasons: dict = {}
        targets = plan_segment_targets(
            [projection_item.segment_id],
            lambda _: projection_item.capture_at,
            lambda _: projection_item.duration_seconds,
            item.owner_id,
            origin,
            target,
            binding.source,
            binding.client_device_id,
            binding.is_locked,
            binding.job_id,
            reasons,
        )
        target, reason = targets.get(projection_item.segment_id), reasons.get(projection_item.segment_id)
        if ambiguous_binding_pending(item.owner_id, reason):
            raise ProjectionBlocked('recording generation binding remains ambiguous')
    elif origin and start is not None and end is not None:
        from utils.sync.recording_session_target import resolve_recording_session_sync_target

        target = resolve_recording_session_sync_target(
            item.owner_id,
            origin,
            binding.source,
            binding.client_device_id,
            binding.is_locked,
            start,
            end,
            firestore_client=client,
        )
    return ResolvedContext(target, reason, geo)
