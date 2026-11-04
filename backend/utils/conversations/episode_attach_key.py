"""Semantic episode input identity with a conservative WAL generation fence."""

from copy import deepcopy
import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from config import episodes as episode_config
from utils.conversations.recorded_time import conversation_span
from utils.conversations.fragment_visibility import is_relevance_discarded


def _json(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, 'model_dump'):
        return value.model_dump()
    raise TypeError(type(value).__name__)


def content_key(row: Mapping[str, Any]) -> str | None:
    """None is uncertainty, never permission to skip. Include every recovery input.

    assignment.assign_in_transaction increments sync_content_revision on every admitted WAL
    merge, including identical text/extent. Pair that conservative fence with a
    transcript/span digest, ancestry and member flags; equal revisions alone
    cannot prove unchanged discard or smart-merge state.
    """
    try:
        span = conversation_span(row)
        if span is None or not isinstance(row.get('transcript_segments'), list):
            return None
        fields = (
            'started_at',
            'finished_at',
            'created_at',
            'source',
            'sync_content_revision',
            'status',
            'structured',
            'summary_blocked_reason',
            'record_lane_owner',
            'record_projection_revision',
            'record_upload_failed',
            'record_audio_partial',
            'episode_transcription_pending_at',
            'episode_transcription_deadline_at',
            'language',
            'calendar_identity',
            'external_data',
            'transcript_segments',
            'discarded',
            'deleted',
            'sync_merged_into',
            'sync_relevance_user_kept',
            'has_photos',
            'photos',
            'user_title',
            'starred',
            'folder_user_set',
            'capture_group',
            'capture_group_member_context',
        )
        value = {field: row.get(field) for field in fields}
        value.update(
            relevance_discarded=is_relevance_discarded(row),
            recorded_start=span.recorded_start,
            recorded_end=span.recorded_end,
            sync_merged_from=sorted(set(row.get('sync_merged_from') or [])),
        )
        return (
            'v2:'
            + hashlib.sha256(json.dumps(value, sort_keys=True, default=_json, allow_nan=False).encode()).hexdigest()
        )
    except (TypeError, ValueError, OverflowError, AttributeError):
        return None


def memo_eligible(row):
    # Donor topology and duplicate recovery require cross-row evidence. Retain
    # their full path until that evidence can be proven by the memo itself.
    return not any(
        row.get(k)
        for k in (
            'sync_merged_from',
            'sync_merged_into',
            'capture_group',
            'capture_group_member_context',
            'deleted',
            'discarded',
        )
    )


def should_schedule(before, after):
    """Compare snapshots, never the object the processor may mutate in place."""
    if not before.get('episode_id'):
        return True
    if not isinstance(after, Mapping):
        if not hasattr(after, 'model_dump'):
            return True
        after = after.model_dump()
        if not isinstance(after, Mapping):
            return True
    # Wire models omit raw relevance/ancestry metadata. Preserve raw fields
    # unless the processor exposes them, and compare visibility explicitly.
    merged = {**before, **after}
    if not merged.get('episode_id'):
        return True
    try:
        old, new = scheduling_key(before), scheduling_key(merged)
    except (TypeError, ValueError, OverflowError, AttributeError):
        return True
    return old is None or new is None or old != new


def process_snapshot(row, conversation):
    values = conversation.model_dump() if hasattr(conversation, 'model_dump') else None
    return deepcopy({**row, **values} if isinstance(values, Mapping) else row)


def scheduling_key(row):
    span = conversation_span(row)
    if span is None:
        return None
    # Processing clocks do not change episode input.
    # Use the proven recorded span, even if finished_at advanced during reprocess.
    fields = (
        'status',
        'summary_blocked_reason',
        'record_lane_owner',
        'record_projection_revision',
        'record_upload_failed',
        'record_audio_partial',
        'episode_transcription_pending_at',
        'episode_transcription_deadline_at',
        'source',
        'transcript_segments',
        'discarded',
        'deleted',
        'sync_merged_into',
        'sync_merged_from',
        'sync_relevance_user_kept',
        'relevance_decision',
        'has_photos',
        'photos',
        'user_title',
        'starred',
        'folder_user_set',
        'capture_group',
        'capture_group_member_context',
    )
    value = {field: row.get(field) for field in fields}
    # Before #24579 (or during its rollback), the composer fingerprints member
    # summaries too. Resolve its capability at the call boundary so either PR
    # can land first, and an env flag alone cannot claim an absent capability.
    settle_enabled = getattr(episode_config, 'episode_compose_settle_enabled', None)
    if not callable(settle_enabled) or not settle_enabled():
        value['structured'] = row.get('structured')
    value.update(recorded_start=span.recorded_start, recorded_end=span.recorded_end)
    return content_key(value)
