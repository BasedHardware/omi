"""Pure boundary and late-speech policy. No switch reads and no IO."""

from utils.conversations.v3 import visibility
from utils.conversations.v3.outline import SILENCE, playback_origin

from copy import deepcopy
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5
from difflib import SequenceMatcher
from typing import Any

CAP = timedelta(hours=2)


def word_count(lines):
    return sum(len(line['text'].split()) for line in lines)


def late_rewrite(*, previous_words, new_words, ended_at, now, rewrites):
    return (
        rewrites == 0
        and new_words > 0
        and timedelta(0) <= now - ended_at <= timedelta(days=1)
        and (new_words >= 100 or new_words >= previous_words * 0.1)
    )


def _capped(lines, sections):
    end = max(line['end'] for line in lines)
    if end - lines[0]['start'] <= CAP:
        return [lines]
    middle = lines[0]['start'] + (end - lines[0]['start']) / 2
    candidates = [i for i in sections if 0 < i < len(lines)] or list(range(1, len(lines)))
    if not candidates:
        raise ValueError('single_transcript_segment_exceeds_two_hours')
    cut = min(candidates, key=lambda i: abs((lines[i]['start'] - middle).total_seconds()))
    return _capped(lines[:cut], []) + _capped(lines[cut:], [])


def windows(groups, outlines):
    result = []
    for group, entries in zip(groups, outlines):
        for index, entry in enumerate(entries):
            begin = entry['first_line'] - 1
            end = entries[index + 1]['first_line'] - 1 if index + 1 < len(entries) else len(group['lines'])
            lines = group['lines'][begin:end]
            sections = [
                s['first_line'] - 1 - begin for s in entry.get('sections', []) if isinstance(s.get('first_line'), int)
            ]
            capped = _capped(lines, sections)
            for part_index, part in enumerate(capped):
                candidate = {
                    **entry,
                    'lines': part,
                    'manual_end': group.get('manual_end', False),
                    'finished': group['finished'] or end < len(group['lines']) or part_index < len(capped) - 1,
                }
                # A model can undo a topic split, never a recorded silence boundary.
                prior = result[-1] if result else None
                if (
                    prior
                    and entry.get('resumes_previous')
                    and not prior.get('manual_end')
                    and prior['kind'] == candidate['kind']
                    and prior.get('people') == candidate.get('people')
                    and max(timedelta(0), part[0]['start'] - max(line['end'] for line in prior['lines'])) < SILENCE
                    and max(max(line['end'] for line in prior['lines']), max(line['end'] for line in part))
                    - prior['lines'][0]['start']
                    <= CAP
                ):
                    prior['lines'].extend(part)
                    prior['finished'] = candidate['finished']
                else:
                    result.append(candidate)
    return result


def build(uid, window, recordings, existing=None):
    lines = window['lines']
    start, end = lines[0]['start'], max(line['end'] for line in lines)
    if existing and existing.get('status') != 'in_progress':
        start, end = existing['started_at'], existing['finished_at']
    cid = existing['id'] if existing else str(uuid5(NAMESPACE_URL, f'v3:{uid}:{start.isoformat()}'))
    first = recordings[lines[0]['conversation_id']]
    segments = []
    for line in lines:
        segment = deepcopy(line['segment'])
        segment.update(start=(line['start'] - start).total_seconds(), end=(line['end'] - start).total_seconds())
        segments.append(segment)
    pieces, files = [], []
    for rid in dict.fromkeys(line['conversation_id'] for line in lines):
        recording = recordings[rid]
        owned = [line for line in lines if line['conversation_id'] == rid]
        left, right = min(l['start'] for l in owned), max(l['end'] for l in owned)
        for af in recording.get('audio_files') or []:
            origin = playback_origin(af, recording)
            duration = float(af.get('duration') or 0)
            a, b = max(0.0, (left - origin).total_seconds()), min(duration, (right - origin).total_seconds())
            if b > a:
                pieces.append({'recording_id': rid, 'audio_file_id': af['id'], 'start': a, 'end': b})
                files.append(
                    {
                        **af,
                        'id': str(uuid5(NAMESPACE_URL, rid + ':' + af['id'])),
                        'recording_id': rid,
                        'recording_file_id': af['id'],
                    }
                )
    if existing and existing.get('status') != 'in_progress':
        # Finished copies own user edits and mixed-source merge speech. Append
        # new recorded lines rather than rebuilding away those edits/windows.
        old_segments = deepcopy(existing.get('transcript_segments') or [])
        keys = {(s.get('id'), s.get('start'), s.get('end')) for s in old_segments}

        def already_present(segment):
            if (segment.get('id'), segment.get('start'), segment.get('end')) in keys:
                return True
            text = ' '.join(segment.get('text', '').casefold().split())
            # Same words are a duplicate only when they overlap the stored line in time; a speaker
            # repeating a sentence a few seconds later is new speech.
            return any(
                segment['start'] <= old.get('end', old['start']) + 2
                and segment.get('end', segment['start']) >= old['start'] - 2
                and (
                    text == ' '.join(old.get('text', '').casefold().split())
                    or (
                        len(text.split()) >= 6
                        and SequenceMatcher(None, text, ' '.join(old.get('text', '').casefold().split())).ratio()
                        >= 0.92
                    )
                )
                for old in old_segments
            )

        segments = old_segments + [s for s in segments if not already_present(s)]
        segments.sort(key=lambda s: s['start'])
        for piece in existing.get('recording_pieces') or []:
            if piece not in pieces:
                pieces.append(piece)
        known_files = {af['id'] for af in files}
        files.extend(af for af in existing.get('audio_files') or [] if af['id'] not in known_files)
    title = (
        (existing or {}).get('structured', {}).get('title') if (existing or {}).get('title_locked') else window['title']
    )
    manual_end = bool(window.get('manual_end') or (existing or {}).get('manual_end'))
    outline_kind = window.get('outline_kind', window['kind'])
    kind, hidden, reason = visibility.project(
        outline_kind,
        recordings,
        {line['conversation_id'] for line in lines},
        words=sum(len(s.get('text', '').split()) for s in segments),
        finished=window['finished'],
        manual_end=manual_end,
    )
    row: dict[str, Any] = {
        **(existing or {}),
        'id': cid,
        'v3_derived': True,
        'manual_end': manual_end,
        'created_at': start,
        'started_at': start,
        'finished_at': end,
        'source': first.get('source', 'omi'),
        # Places and detail read the conversation, not the hidden recording: carry its location.
        'geolocation': (existing or {}).get('geolocation')
        or next(
            (
                recordings[rid]['geolocation']
                for rid in dict.fromkeys(l['conversation_id'] for l in lines)
                if recordings[rid].get('geolocation')
            ),
            None,
        ),
        'language': first.get('language'),
        # The copy keeps the strongest protection of any contributing recording (as sync merges do),
        # and never drops below what the conversation already has.
        'data_protection_level': (
            'enhanced'
            if any(
                level == 'enhanced'
                for level in [(existing or {}).get('data_protection_level')]
                + [
                    recordings[rid].get('data_protection_level')
                    for rid in dict.fromkeys(l['conversation_id'] for l in lines)
                ]
            )
            else first.get('data_protection_level', 'standard')
        ),
        # Custom-STT provenance follows the words: any contributing custom-STT recording marks the copy.
        'uses_custom_stt': bool(
            (existing or {}).get('uses_custom_stt')
            or any(recordings[l['conversation_id']].get('uses_custom_stt') for l in lines)
        ),
        'private_cloud_sync_enabled': bool(first.get('private_cloud_sync_enabled')),
        'is_locked': (
            existing['is_locked']
            if existing and 'is_locked' in existing
            else any(recordings[l['conversation_id']].get('is_locked', False) for l in lines)
        ),
        'status': 'processing' if window['finished'] else 'in_progress',
        'discarded': bool((existing or {}).get('discarded')),
        'kind': kind,
        'outline_kind': outline_kind,
        'home_hidden_reason': reason,
        'home_hidden': hidden,
        'title_locked': bool(
            (existing or {}).get('title_locked')
            or (title and (not hidden or not window['finished']) and kind not in {'media', 'background'})
        ),
        'tile_state': 'writing' if window['finished'] else 'live',
        'v3_recording_ids': list(dict.fromkeys(l['conversation_id'] for l in lines)),
        'transcript_segments': segments,
        'recording_pieces': pieces,
        'audio_files': files,
        'structured': {
            **(existing or {}).get('structured', {}),
            'title': title or '',
            'overview': (existing or {}).get('structured', {}).get('overview') or window['line'],
            'emoji': (
                (existing or {}).get('structured', {}).get('emoji')
                if (existing or {}).get('title_locked')
                else window.get('emoji', '💬')
            ),
        },
    }
    if not (existing or {}).get('summary_covers_through'):
        row['structured']['sections'] = [
            {'heading': str(s.get('title') or '')[:120], 'body_markdown': ''} for s in window.get('sections') or []
        ]
        row['structured']['participants'] = [{'name': name} for name in window.get('people') or []]
    if existing and segments != existing.get('transcript_segments'):
        row['sync_content_revision'] = int(existing.get('sync_content_revision') or 0) + 1
    elif not existing:
        row['sync_content_revision'] = 1
    row['v3_recording_ids'] = list(
        dict.fromkeys([*(existing or {}).get('v3_recording_ids', []), *row['v3_recording_ids']])
    )
    row['_v3_claims'] = {}
    for rid in row['v3_recording_ids']:
        held = [c for c in recordings.get(rid, {}).get('claims') or [] if c['conversation_id'] == cid]
        if existing and existing.get('status') != 'in_progress' and held:
            row['_v3_claims'][rid] = [{'start': c['start'], 'end': c['end']} for c in held]
        else:
            owned = [line for line in lines if line['conversation_id'] == rid]
            if owned:
                row['_v3_claims'][rid] = [
                    {'start': min(l['start'] for l in owned), 'end': max(l['end'] for l in owned)}
                ]
    row.pop('updated_at', None)
    return row


def preserve_finished_windows(planned, existing, recordings=None):
    """Late speech cannot move a published finished conversation's boundaries."""
    finished = [
        r
        for r in existing.values()
        if r.get('status') != 'in_progress' and r.get('started_at') and r.get('finished_at')
    ]
    retained, fresh = {}, []
    for window in planned:
        gaps = []
        for line in window['lines']:
            claims = (recordings or {}).get(line['conversation_id'], {}).get('claims')
            owner = next(
                (
                    r
                    for r in finished
                    if r['started_at'] <= line['start']
                    and line['end'] <= r['finished_at']
                    and (
                        claims is None
                        or any(
                            c['conversation_id'] == r['id'] and c['start'] <= line['start'] and line['end'] <= c['end']
                            for c in claims
                        )
                    )
                ),
                None,
            )
            if owner:
                if gaps:
                    fresh.append({**window, 'lines': gaps})
                    gaps = []
                target = retained.setdefault(
                    owner['id'],
                    {
                        **window,
                        'lines': [],
                        'finished': True,
                        'title': owner.get('structured', {}).get('title', ''),
                        'kind': owner.get('outline_kind') or owner.get('kind', 'conversation'),
                        'emoji': owner.get('structured', {}).get('emoji', '💬'),
                        'existing_id': owner['id'],
                    },
                )
                target['lines'].append(line)
            else:
                gaps.append(line)
        if gaps:
            fresh.append({**window, 'lines': gaps})
    return sorted([*retained.values(), *fresh], key=lambda w: w['lines'][0]['start'])
