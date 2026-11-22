"""Pure boundary and late-speech policy. No switch reads and no IO."""

from utils.conversations.v3 import policy, visibility
from utils.conversations.v3.outline import SILENCE, playback_origin

from collections.abc import Iterator
from copy import deepcopy
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5
from difflib import SequenceMatcher
from itertools import groupby
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


def _as_sections(entries: list[dict[str, Any]], *, primary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    first = entries[0]
    # Participating speech determines the card when it shares a stretch with passive audio.
    priority = {'conversation': 0, 'voice_work': 1}
    keep_later_primary_section = primary is None
    primary = primary or min(entries, key=lambda entry: priority.get(entry['kind'], 2))
    sections = []
    for entry in entries:
        if entry is not primary or (keep_later_primary_section and entry is not first):
            sections.append({'first_line': entry['first_line'], 'title': entry['title']})
        sections.extend(entry.get('sections') or [])
    return [
        {
            **primary,
            'first_line': first['first_line'],
            'line': primary.get('line') or next((entry['line'] for entry in entries if entry.get('line')), ''),
            'resumes_previous': (
                first.get('resumes_previous', False)
                if keep_later_primary_section
                else all(entry.get('resumes_previous') for entry in entries)
            ),
            'people': list(dict.fromkeys(name for entry in entries for name in entry.get('people') or [])),
            'sections': sections,
        }
    ]


def _fold_participating_topics(entries, counts):
    buckets: list[list[dict[str, Any]]] = []
    leading = []
    for entry in entries:
        if counts[entry['first_line']] >= visibility.MIN_HOME_WORDS:
            buckets.append([*leading, entry])
            leading = []
        elif buckets:
            buckets[-1].append(entry)
        else:
            leading.append(entry)
    if leading:
        buckets.append(leading)
    for bucket in buckets:
        if len(bucket) == 1:
            yield bucket[0]
        else:
            primary = max(bucket, key=lambda entry: counts[entry['first_line']])
            yield _as_sections(bucket, primary=primary)[0]


def _fold_short_topics(lines: list, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    starts = [entry['first_line'] - 1 for entry in entries]
    counts = {start + 1: word_count(lines[start:end]) for start, end in zip(starts, starts[1:] + [len(lines)])}
    result = []
    # Media and background retain their independent Home visibility and wearer evidence.
    for participating, topics in groupby(entries, key=lambda entry: entry['kind'] in {'conversation', 'voice_work'}):
        result.extend(_fold_participating_topics(topics, counts) if participating else topics)
    return result


def _cohesive_groups(groups, outlines) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    for group, entries in zip(groups, outlines):
        if not entries:
            continue
        manual = group.get('manual_end') or group.get('after_manual_end')
        cut_points = [entry['first_line'] - 1 for entry in entries]
        cut_points.extend(
            section['first_line'] - 1
            for entry in entries
            for section in entry.get('sections') or []
            if isinstance(section.get('first_line'), int)
        )
        parts = _capped(group['lines'], cut_points)
        start = 1
        for index, part in enumerate(parts):
            end = start + len(part)
            active = [entry for entry in entries if entry['first_line'] < end]
            first = max(i for i, entry in enumerate(active) if entry['first_line'] <= start)
            topics = [
                {
                    **entry,
                    'first_line': max(entry['first_line'], start) - start + 1,
                    'sections': [
                        {**section, 'first_line': section['first_line'] - start + 1}
                        for section in entry.get('sections') or []
                        if isinstance(section.get('first_line'), int) and start <= section['first_line'] < end
                    ],
                }
                for entry in active[first:]
            ]
            last = index == len(parts) - 1
            bounded = {
                **group,
                'lines': part,
                'manual_end': bool(last and group.get('manual_end')),
                '_keep_unmatched_together': bool(manual),
                'finished': group['finished'] or not last,
                '_stretch_words': word_count(part),
            }
            yield bounded, _as_sections(topics) if manual else _fold_short_topics(part, topics)
            start = end


def windows(groups, outlines, *, cohesion=False):
    result = []
    pairs = _cohesive_groups(groups, outlines) if cohesion else zip(groups, outlines)
    for group, entries in pairs:
        first_result = len(result)
        if len(entries) > 1 and (group.get('manual_end') or group.get('after_manual_end')):
            entries = _as_sections(entries)
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
                    'manual_end': bool(
                        group.get('manual_end') and end == len(group['lines']) and part_index == len(capped) - 1
                    ),
                    '_keep_unmatched_together': bool(
                        group.get('_keep_unmatched_together')
                        or group.get('manual_end')
                        or group.get('after_manual_end')
                    ),
                    'finished': group['finished'] or end < len(group['lines']) or part_index < len(capped) - 1,
                }
                if cohesion:
                    candidate['_stretch_words'] = group['_stretch_words']
                    candidate['_stretch_partition'] = first_result
                # A model can undo a topic split, never a recorded silence boundary.
                prior = result[-1] if result else None
                if (
                    prior
                    and (not cohesion or len(result) > first_result)
                    and entry.get('resumes_previous')
                    and not prior.get('manual_end')
                    and prior['kind'] == candidate['kind']
                    and prior.get('people') == candidate.get('people')
                    and max(timedelta(0), part[0]['start'] - max(line['end'] for line in prior['lines'])) < SILENCE
                    and max(max(line['end'] for line in prior['lines']), max(line['end'] for line in part))
                    - prior['lines'][0]['start']
                    <= CAP
                ):
                    if cohesion:
                        prior['sections'] = _as_sections([prior, candidate], primary=prior)[0]['sections']
                    prior['lines'].extend(part)
                    prior['finished'] = candidate['finished']
                    prior['manual_end'] = candidate['manual_end']
                else:
                    result.append(candidate)
    return result


def _unowned_spans(start, end, occupied):
    cursor = start
    for left, right in sorted(occupied):
        if left >= end:
            break
        if right <= cursor:
            continue
        if cursor < left:
            yield cursor, left
        cursor = max(cursor, right)
    if cursor < end:
        yield cursor, end


def build(uid, window, recordings, existing=None, *, allocated=None):
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
    pieces, files, claims = [], [], {}
    published = window.get('_published', {})
    retained = existing and existing.get('status') != 'in_progress'
    for rid in dict.fromkeys(line['conversation_id'] for line in lines):
        recording = recordings[rid]
        owned = [line for line in lines if line['conversation_id'] == rid]
        left, right = min(l['start'] for l in owned), max(l['end'] for l in owned)
        occupied = published.get(rid, {})
        held = [(c['start'], c['end']) for c in recording.get('claims') or [] if c['conversation_id'] == cid]
        if retained and held:
            spans = sorted(set(held))
        else:
            blocked_claims = [*occupied.get('claims', ()), *(allocated or {}).get(rid, ())]
            spans = list(_unowned_spans(left, right, blocked_claims))
            if left == right and not any(a <= left < b for a, b in blocked_claims):
                spans = [(left, right)]
        claims[rid] = [{'start': a, 'end': b} for a, b in spans]
        for af in recording.get('audio_files') or []:
            origin = playback_origin(af, recording)
            duration = float(af.get('duration') or 0)
            blocked = occupied.get('files', {}).get(af['id'], ())
            file_pieces = []
            for start_at, end_at in spans:
                a = max(0.0, (max(left, start_at) - origin).total_seconds())
                b = min(duration, (min(right, end_at) - origin).total_seconds())
                file_pieces.extend(_unowned_spans(a, b, blocked))
            if file_pieces:
                pieces.extend(
                    {'recording_id': rid, 'audio_file_id': af['id'], 'start': a, 'end': b} for a, b in file_pieces
                )
                files.append(
                    {
                        **af,
                        'id': str(uuid5(NAMESPACE_URL, rid + ':' + af['id'])),
                        'recording_id': rid,
                        'recording_file_id': af['id'],
                    }
                )
    if existing is not None and retained:
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
    words = window.get('_stretch_words', sum(len(s.get('text', '').split()) for s in segments))
    if (
        existing is not None
        and retained
        and window.get('_stretch_partition') is not None
        and existing.get('home_hidden') is False
        and existing.get('home_hidden_reason') in {'conversation', 'wearer_recognition_uncertain'}
    ):
        # Finished visible speech already passed the word gate, possibly on its original stretch.
        # Passive, manual and wearer-recognition rules still apply to the current projection.
        words = max(words, visibility.MIN_HOME_WORDS)
    kind, hidden, reason = visibility.project(
        outline_kind,
        recordings,
        {line['conversation_id'] for line in lines},
        words=words,
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
        row['structured']['participants'] = [
            {'name': name, 'source': 'transcript'} for name in window.get('people') or []
        ]
    if existing and segments != existing.get('transcript_segments'):
        row['sync_content_revision'] = int(existing.get('sync_content_revision') or 0) + 1
    elif not existing:
        row['sync_content_revision'] = 1
    row['v3_recording_ids'] = list(
        dict.fromkeys([*(existing or {}).get('v3_recording_ids', []), *row['v3_recording_ids']])
    )
    row['_v3_claims'] = claims
    if retained:
        for rid in row['v3_recording_ids']:
            if rid not in claims:
                held = {
                    (c['start'], c['end'])
                    for c in recordings.get(rid, {}).get('claims') or []
                    if c['conversation_id'] == cid
                }
                if held:
                    claims[rid] = [{'start': a, 'end': b} for a, b in sorted(held)]
    if window['finished']:
        row.pop(policy.LIVE_SUMMARY_FIELD, None)
    row.pop('updated_at', None)
    return row


def _contains_line(row, line, spans):
    inside_window = row['started_at'] <= line['start'] and line['end'] <= row['finished_at']
    if not inside_window:
        return False
    if spans is None or any(a <= line['start'] and line['end'] <= b for a, b in spans):
        return True
    # A previous pass may have published this segment with a clipped audio claim.
    # Its original timing and id still identify the segment on retry.
    segment_id = line['segment'].get('id')
    if not any(a < line['end'] and line['start'] < b for a, b in spans):
        return False
    start = (line['start'] - row['started_at']).total_seconds()
    end = (line['end'] - row['started_at']).total_seconds()
    return any(
        (s.get('id'), s.get('start'), s.get('end')) == (segment_id, start, end)
        and (segment_id is not None or s.get('text') == line['segment'].get('text'))
        for s in row.get('transcript_segments') or []
    )


def preserve_finished_windows(planned, existing, recordings=None):
    """Late speech cannot move a published finished conversation's boundaries."""
    finished = [
        r
        for r in existing.values()
        if r.get('status') != 'in_progress' and r.get('started_at') and r.get('finished_at')
    ]
    protected = {r['id'] for r in finished}
    published_ids = set()
    claims_by_recording = {}
    published = {}
    for rid, recording in (recordings or {}).items():
        if recording.get('claims') is None:
            continue
        indexed = claims_by_recording.setdefault(rid, {})
        for claim in recording['claims']:
            if claim['conversation_id'] in protected:
                span = (claim['start'], claim['end'])
                indexed.setdefault(claim['conversation_id'], []).append(span)
                published.setdefault(rid, {}).setdefault('claims', []).append(span)
                published_ids.add(claim['conversation_id'])
    for row in finished:
        for p in row.get('recording_pieces') or []:
            published_ids.add(row['id'])
            files = published.setdefault(p['recording_id'], {}).setdefault('files', {})
            files.setdefault(p['audio_file_id'], []).append((p['start'], p['end']))
    retained, fresh = {}, []
    published_partitions = set()
    fresh_metadata = {'_published': published, '_published_ids': published_ids}
    for window in planned:
        gaps = []
        partition = window.get('_stretch_partition')
        for line in window['lines']:
            claims = claims_by_recording.get(line['conversation_id'])
            owner = next(
                (r for r in finished if _contains_line(r, line, None if claims is None else claims.get(r['id'], ()))),
                None,
            )
            if partition is not None and partition not in published_partitions:
                spans = published.get(line['conversation_id'], {}).get('claims', ())
                if owner or any(a < line['end'] and line['start'] < b for a, b in spans):
                    published_partitions.add(partition)
            if owner:
                if gaps and not window.get('_keep_unmatched_together'):
                    fresh.append({**window, **fresh_metadata, 'lines': gaps, 'manual_end': False})
                    gaps = []
                target = retained.setdefault(
                    owner['id'],
                    {
                        **window,
                        'lines': [],
                        'finished': True,
                        'manual_end': False,
                        'title': owner.get('structured', {}).get('title', ''),
                        'kind': owner.get('outline_kind') or owner.get('kind', 'conversation'),
                        'emoji': owner.get('structured', {}).get('emoji', '💬'),
                        'existing_id': owner['id'],
                    },
                )
                target.pop('_stretch_words', None)
                target['lines'].append(line)
                if line is window['lines'][-1] and window.get('manual_end'):
                    target['manual_end'] = True
            else:
                gaps.append(line)
        if gaps:
            fresh.append(
                {
                    **window,
                    **fresh_metadata,
                    'lines': gaps,
                    'manual_end': bool(window.get('manual_end') and gaps[-1] is window['lines'][-1]),
                }
            )
    # Even a separate fresh topic in the same stretch cannot qualify on published speech.
    for window in fresh:
        if window.get('_stretch_partition') in published_partitions:
            window.pop('_stretch_words', None)
    return sorted([*retained.values(), *fresh], key=lambda w: w['lines'][0]['start'])
