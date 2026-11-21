"""Conservative merge-only refinement over already published v3 claims."""

from copy import deepcopy
from datetime import timedelta
import json
from typing import Any

from utils.conversations.smart_merge_policy import user_managed
from utils.conversations.summary_selection import render_sections_markdown
from utils.conversations.v3 import planner
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_FIELD


def _eligible(row):
    return (
        row.get('v3_derived')
        and row.get('status') == 'completed'
        and row.get('started_at')
        and row.get('finished_at')
        and row.get('summary_covers_through')
        and row['summary_covers_through'] >= row['finished_at']
        and row.get('kind') in {'conversation', 'voice_work'}
        and row.get('visibility', 'private') == 'private'
        and not row.get('home_hidden')
        and not user_managed(row)
        and not (row.get('structured') or {}).get('note_claims')
        and row.get('finalization_status') != 'dead_letter'
        and not any(
            row.get(key)
            for key in (
                'deleted',
                'recording',
                'discarded',
                'dream_duplicate_of',
                'summary_retryable',
                'manual_end',
                'backfilled',
                'v3_backfill_run',
                'v3_unlocked',
                'v3_process_pending',
                'v3_process_failed',
                'v3_created_pending',
                'sync_merged_into',
                'v3_claims_transferred_to',
                'external_data',
                'user_corrections',
                'apps_results',
                'episode_id',
                'client_processing',
                'folder_id',
                'photos',
            )
        )
    )


def _segment_key(segment, start, end):
    return segment.get('id'), start, end, segment.get('text')


def _offset(seconds):
    return timedelta(seconds=float(seconds or 0))


def _absolute(row, segment):
    start = row['started_at'] + _offset(segment.get('start'))
    return start, max(start, row['started_at'] + _offset(segment.get('end')))


def _owned_claims(rows, recordings):
    owners = {row['id'] for row in rows}
    claims = {}
    for row in rows:
        source_ids = set(row.get('v3_recording_ids') or ())
        if not source_ids or any(
            piece['recording_id'] not in source_ids for piece in row.get('recording_pieces') or ()
        ):
            return None
        for rid in sorted(source_ids):
            recording = recordings.get(rid)
            if not recording or recording.get('deleted') or recording.get('sync_merged_into'):
                return None
            if recording.get('is_locked') or (
                recording.get('data_protection_level') == 'enhanced' and row.get('data_protection_level') != 'enhanced'
            ):
                return None
            if not any(claim['conversation_id'] == row['id'] for claim in recording.get('claims') or ()):
                return None
            claims[rid] = [claim for claim in recording.get('claims') or () if claim['conversation_id'] in owners]
    for rid, recording in recordings.items():
        for claim in recording.get('claims') or ():
            if claim['conversation_id'] in owners and claim not in claims.get(rid, ()):
                return None
    return claims


def _union_claims(claims):
    union = []
    for start, end in sorted({(claim['start'], claim['end']) for claim in claims}):
        # Keep touching spans separate: a gap may be zero, but a boundary can
        # still exist between two distinct ranges of the same recording.
        if union and start < union[-1]['end']:
            union[-1]['end'] = max(end, union[-1]['end'])
        else:
            union.append({'start': start, 'end': end})
    return union


def _merged_row(rows, claims):
    winner = rows[0]
    merged = deepcopy(winner)
    sections: list[dict[str, Any]] = []
    segments = {}
    files = {}
    pieces = []
    for row in rows:
        for segment in row['transcript_segments']:
            start, end = _absolute(row, segment)
            segments.setdefault(
                _segment_key(segment, start, end),
                {
                    **segment,
                    'start': (start - winner['started_at']).total_seconds(),
                    'end': (end - winner['started_at']).total_seconds(),
                },
            )
        for file in row.get('audio_files') or ():
            files.setdefault(file['id'], file)
        pieces.extend(row.get('recording_pieces') or ())
    for row in rows:
        structured = row['structured']
        row_sections = structured.get('sections') or []
        overview = structured.get('overview')
        if (
            isinstance(overview, str)
            and overview.strip()
            and overview.strip() != render_sections_markdown(row_sections)
        ):
            sections.append({'heading': structured.get('title') or '', 'body_markdown': overview})
        sections.extend(row_sections)
        if row is winner:
            continue
        for field in ('action_items', 'events', 'participants', 'insights'):
            current = list(merged['structured'].get(field) or ())
            for item in structured.get(field) or ():
                if item not in current:
                    current.append(item)
            if current:
                merged['structured'][field] = current
    merged['structured']['sections'] = sections
    merged['structured']['overview'] = render_sections_markdown(sections)
    end = max(row['finished_at'] for row in rows)
    merged.update(
        finished_at=end,
        summary_covers_through=end,
        transcript_segments=sorted(segments.values(), key=lambda segment: segment['start']),
        recording_pieces=planner.nonoverlapping_pieces(pieces),
        audio_files=list(files.values()),
        v3_recording_ids=list(claims),
        sync_content_revision=int(winner.get('sync_content_revision') or 0) + 1,
        _v3_claims={rid: _union_claims(spans) for rid, spans in claims.items()},
        v3_refined=True,
        _v3_absorbed=[row['id'] for row in rows[1:]],
    )
    return merged


def candidate(windows, existing, recordings):
    """Return one fully covered refinement, or leave the ordinary projection intact."""
    eligible = sorted(
        (row for row in existing.values() if _eligible(row)),
        key=lambda row: (row['started_at'], row['id']),
    )
    if len(eligible) < 2:
        return None
    for index, window in enumerate(windows):
        if not window['finished'] or window.get('manual_end'):
            continue
        left = window['lines'][0]['start']
        right = max(line['end'] for line in window['lines'])
        rows = [
            row
            for row in eligible
            if left <= row['started_at'] and row['finished_at'] <= right and row['kind'] == window['kind']
        ]
        # Bound one atomic refinement per pass. Additional candidates stay intact.
        if not 2 <= len(rows) <= 8 or any(
            row.get('v3_open_locked') or row.get(OPEN_LOOP_EXTRACTIONS_FIELD) for row in rows[1:]
        ):
            continue
        members = {row['id'] for row in rows}
        if any(
            row['id'] not in members
            and not row.get('deleted')
            and row.get('started_at')
            and row.get('finished_at')
            and left < row['finished_at']
            and row['started_at'] < right
            for row in existing.values()
        ):
            continue
        flags = ('data_protection_level', 'private_cloud_sync_enabled', 'uses_custom_stt')
        if any(row.get(flag) != rows[0].get(flag) for row in rows[1:] for flag in flags):
            continue
        # A user overview edit deletes generated sections. Older edits have no
        # separate provenance marker, so preserve sectionless cards in place.
        if any(
            not isinstance(row.get('structured'), dict)
            or not isinstance(row['structured'].get('sections'), list)
            or not row['structured']['sections']
            or not row.get('transcript_segments')
            for row in rows
        ):
            continue
        claims = _owned_claims(rows, recordings)
        if claims is None:
            continue
        if any(span['start'] < left or right < span['end'] for spans in claims.values() for span in spans):
            continue
        # The outline must cover every published segment, and no novel speech.
        # A shifted or edited line is left to ordinary, fixed-boundary projection.
        previous = {
            _segment_key(segment, *_absolute(row, segment)) for row in rows for segment in row['transcript_segments']
        }
        proposed = {_segment_key(line['segment'], line['start'], line['end']) for line in window['lines']}
        if proposed != previous or any(
            not any(
                claim['start'] <= line['start'] and line['end'] <= claim['end']
                for claim in claims.get(line['conversation_id'], ())
            )
            for line in window['lines']
        ):
            continue
        merged = _merged_row(rows, claims)
        # Leave headroom for encoding and indexing. An optional refinement must
        # not make an otherwise healthy owner exceed a Firestore document limit.
        if len(json.dumps(merged, default=str).encode()) <= 384 * 1024:
            return index, merged
    return None
