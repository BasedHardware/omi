"""Pure eligibility and transcript surgery for administrative smart-merge undo."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping, Sequence

from utils.conversations.smart_merge_policy import ledger_fragments, refresh_owed, revision, smart_merge_state


def unmerge_suffix(survivor: Mapping[str, Any], donor_id: str) -> list[str]:
    fragments = ledger_fragments(survivor)
    for index, fragment in enumerate(fragments):
        if index > 0 and fragment.id == donor_id:
            return [item.id for item in fragments[index:]]
    return []


def unmerge_ineligible(
    survivor: Mapping[str, Any], donors: Sequence[Mapping[str, Any]], *, force: bool, now: datetime
) -> str | None:
    if not survivor or survivor.get('deleted'):
        return 'survivor_missing_or_deleted'
    state = smart_merge_state(survivor)
    if state.get('role') != 'survivor' or survivor.get('status') != 'completed':
        return 'survivor_not_completed'
    if refresh_owed(survivor):
        return 'survivor_refresh_owed'
    if state.get('unmerge_pending'):
        return 'unmerge_pending'
    until = (state.get('refresh_lease') or {}).get('until')
    if isinstance(until, datetime) and until > now:
        return 'survivor_lease_busy'
    # Merge admission excludes these fields, so their presence means curation
    # since a merge. Legacy rows have no title-edit timestamp: fail closed.
    if not force and (isinstance(survivor.get('user_title'), str) or survivor.get('manual_speaker_assignments')):
        return 'survivor_user_modified'
    if not donors:
        return 'donor_not_in_ledger'
    for donor in donors:
        donor_state = smart_merge_state(donor)
        if donor_state.get('role') != 'donor' or donor_state.get('survivor_id') != survivor.get('id'):
            return 'donor_not_owned'
        if not donor.get('deleted') or donor.get('sync_merged_into') != survivor.get('id'):
            return 'donor_not_owned'
        if donor.get('sync_bridge_cleaned_revision') != donor.get('sync_content_revision'):
            return 'donor_cleanup_pending'
        if donor.get('sync_content_revision') is None:
            return 'donor_cleanup_pending'
    return None


def unmerge_payload(
    survivor: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
    donors: Sequence[tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]],
    *,
    now: datetime,
) -> tuple[dict[str, Any], int]:
    """Remove the suffix by stable ids, with bounded time windows for missing ids.

    A donor with some missing ids needs a window as well: refreshed legacy
    segments may have acquired ids that the original donor never carried.
    Never match text or speaker labels.
    """
    fragments = ledger_fragments(survivor)
    donor_ids = {str(row['id']) for row, _ in donors}
    removed_fragments = [fragment for fragment in fragments if fragment.id in donor_ids]
    kept = [fragment for fragment in fragments if fragment.id not in donor_ids]
    origin = survivor.get('started_at')
    if not isinstance(origin, datetime) or not kept or len(removed_fragments) != len(donors):
        raise ValueError('invalid_fragment_windows')
    ids = {str(segment['id']) for _, items in donors for segment in items if segment.get('id')}
    windows = [
        (fragment.started_at.timestamp() - origin.timestamp(), fragment.finished_at.timestamp() - origin.timestamp())
        for fragment in removed_fragments
    ]
    fallback_windows = [
        windows[index]
        for index, (_, items) in enumerate(donors)
        if not items or any(not segment.get('id') for segment in items)
    ]
    retained = []
    for segment in segments:
        sid, start = segment.get('id'), segment.get('start')
        if sid and str(sid) in ids:
            continue
        candidate_windows = fallback_windows if sid else windows
        if candidate_windows:
            if not isinstance(start, (int, float)) or not math.isfinite(start):
                raise ValueError('invalid_segment_time')
            if any(floor <= start <= ceiling for floor, ceiling in candidate_windows):
                continue
        retained.append(dict(segment))
    state = dict(smart_merge_state(survivor))
    next_revision = revision(survivor) + 1
    state.update(
        revision=next_revision,
        fragments=[fragment.as_ledger_entry() for fragment in kept],
        unmerge_pending={
            'donor_ids': [str(row['id']) for row, _ in donors],
            'revision': next_revision,
            'unmerged_at': now,
        },
    )
    state.pop('refresh_lease', None)
    return {
        'transcript_segments': retained,
        'finished_at': max(fragment.finished_at for fragment in kept),
        'sync_merged_from': [cid for cid in survivor.get('sync_merged_from', []) if cid not in donor_ids],
        'sync_content_revision': int(survivor.get('sync_content_revision') or 0) + 1,
        'smart_merge': state,
    }, len(segments) - len(retained)
