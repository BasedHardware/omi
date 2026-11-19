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
                'locked': group.get('locked', group['finished']) or not last,
                '_stretch_words': word_count(part),
            }
            yield bounded, _as_sections(topics) if manual else _fold_short_topics(part, topics)
            start = end


def windows(groups, outlines, *, cohesion=False, silence_gap=SILENCE, defer_topic_lock=False):
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
                    'finished': (group['finished'] or end < len(group['lines']) or part_index < len(capped) - 1),
                }
                if defer_topic_lock and not group.get('locked', group['finished']) and part_index == len(capped) - 1:
                    candidate['_defer_lock'] = True
                    candidate['_lock_end'] = group['end']
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
                    and max(timedelta(0), part[0]['start'] - max(line['end'] for line in prior['lines'])) < silence_gap
                    and max(max(line['end'] for line in prior['lines']), max(line['end'] for line in part))
                    - prior['lines'][0]['start']
                    <= CAP
                ):
                    if cohesion:
                        prior['sections'] = _as_sections([prior, candidate], primary=prior)[0]['sections']
                    prior['lines'].extend(part)
                    prior['finished'] = candidate['finished']
                    prior['manual_end'] = candidate['manual_end']
                    if defer_topic_lock:
                        prior['_defer_lock'] = candidate.get('_defer_lock', False)
                        if candidate.get('_defer_lock'):
                            prior['_lock_end'] = candidate['_lock_end']
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


def nonoverlapping_pieces(pieces):
    result = []
    occupied = {}
    for piece in pieces:
        key = piece['recording_id'], piece['audio_file_id']
        spans = occupied.setdefault(key, [])
        for start, end in list(_unowned_spans(piece['start'], piece['end'], spans)):
            result.append({**piece, 'start': start, 'end': end})
            spans.append((start, end))
    return result


def is_unlocked(row):
    return row.get('status') == 'in_progress' or bool(row.get('v3_unlocked'))


def build(uid, window, recordings, existing=None, *, allocated=None):
    lines = window['lines']
    start, end = lines[0]['start'], max(line['end'] for line in lines)
    if existing and (not is_unlocked(existing) or window.get('_held_provisional')):
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
    retained = existing and not is_unlocked(existing)
    for rid in dict.fromkeys(line['conversation_id'] for line in lines):
        recording = recordings[rid]
        owned = [line for line in lines if line['conversation_id'] == rid]
        left, right = min(l['start'] for l in owned), max(l['end'] for l in owned)
        occupied = published.get(rid, {})
        held = [(c['start'], c['end']) for c in recording.get('claims') or [] if c['conversation_id'] == cid]
        if (retained or window.get('_held_provisional')) and held:
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
        previous_pieces = existing.get('recording_pieces') or []
        if existing.get('v3_refined'):
            pieces = nonoverlapping_pieces([*previous_pieces, *pieces])
        else:
            pieces.extend(piece for piece in previous_pieces if piece not in pieces)
        known_files = {af['id'] for af in files}
        files.extend(af for af in existing.get('audio_files') or [] if af['id'] not in known_files)
    prior = existing or {}
    structured = prior.get('structured', {})
    preview = bool(window.get('_title_preview') or prior.get('v3_unlocked'))
    title_locked = bool(prior.get('title_locked') and (not preview or prior.get('user_title')))
    title = (prior.get('user_title') if preview else None) or (
        structured.get('title') if title_locked else window['title']
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
        finished=window['finished'] and not window.get('_title_preview'),
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
            title_locked
            or (
                not window.get('_title_preview')
                and title
                and (not hidden or not window['finished'])
                and kind not in {'media', 'background'}
            )
        ),
        'tile_state': 'writing' if window['finished'] and not window.get('_title_preview') else 'live',
        'v3_recording_ids': list(dict.fromkeys(l['conversation_id'] for l in lines)),
        'transcript_segments': segments,
        'recording_pieces': pieces,
        'audio_files': files,
        'structured': {
            **(existing or {}).get('structured', {}),
            'title': title or '',
            'overview': (window['line'] if preview else structured.get('overview')) or window['line'],
            'emoji': structured.get('emoji') if title_locked else window.get('emoji', '💬'),
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
    if retained or window.get('_held_provisional'):
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


def unavailable_preview(row, recordings):
    """Settle an unprojectable preview without releasing any of its old audio claims."""
    return {
        **row,
        'status': 'completed',
        'tile_state': 'done',
        'home_hidden': True,
        'home_hidden_reason': 'source_unavailable',
        'v3_unlocked': False,
        'v3_process_pending': False,
        '_v3_claims': {
            rid: [
                {'start': claim['start'], 'end': claim['end']}
                for claim in recordings.get(rid, {}).get('claims') or ()
                if claim['conversation_id'] == row['id']
            ]
            for rid in row.get('v3_recording_ids') or ()
        },
    }


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


def preserve_finished_windows(planned, existing, recordings=None, *, protect_provisional=False):
    """Late speech cannot move a published finished conversation's boundaries."""
    finished = [
        row
        for row in existing.values()
        if not is_unlocked(row)
        and row.get('started_at')
        and row.get('finished_at')
        and not (row.get('v3_refined') and row.get('v3_claims_transferred_to'))
    ]
    # When an updated outline joins multiple provisional owners, retain their
    # custody independently until lock and ordinary merge-only refinement.
    provisional = set()
    if protect_provisional:
        open_rows = [row for row in existing.values() if row.get('v3_unlocked') and not row.get('deleted')]
        for window in planned:
            left = window['lines'][0]['start']
            right = max(line['end'] for line in window['lines'])
            overlaps = [row for row in open_rows if left < row['finished_at'] and row['started_at'] < right]
            if len(overlaps) > 1:
                provisional.update(row['id'] for row in overlaps)
        finished.extend(row for row in open_rows if row['id'] in provisional)
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
        gaps, pieces = [], []
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
                    pieces.append({**window, **fresh_metadata, 'lines': gaps, 'manual_end': False})
                    gaps = []
                target = retained.setdefault(
                    owner['id'],
                    {
                        **window,
                        'lines': [],
                        'finished': owner['id'] not in provisional,
                        '_held_provisional': owner['id'] in provisional,
                        '_defer_lock': owner['id'] in provisional and window.get('_defer_lock', False),
                        'manual_end': False,
                        'title': owner.get('structured', {}).get('title', ''),
                        'kind': owner.get('outline_kind') or owner.get('kind', 'conversation'),
                        'emoji': owner.get('structured', {}).get('emoji', '💬'),
                        'existing_id': owner['id'],
                    },
                )
                target.pop('_stretch_words', None)
                target['lines'].append(line)
                target['finished'] = target['finished'] or window['finished']
                if not window.get('_defer_lock'):
                    target['_defer_lock'] = False
                if line is window['lines'][-1] and window.get('manual_end'):
                    target['manual_end'] = True
            else:
                gaps.append(line)
        if gaps:
            pieces.append(
                {
                    **window,
                    **fresh_metadata,
                    'lines': gaps,
                    'manual_end': bool(window.get('manual_end') and gaps[-1] is window['lines'][-1]),
                }
            )
        # Published speech follows every fragment but the last, so only the last can be the open edge.
        # Several open fragments never commit (multiple_open_conversations parks the owner), and the
        # fragments, their lines and their time matching stay exactly as a finished window splits.
        for piece in pieces[:-1]:
            piece['finished'] = True
        fresh.extend(pieces)
    # Even a separate fresh topic in the same stretch cannot qualify on published speech.
    for window in fresh:
        if window.get('_stretch_partition') in published_partitions:
            window.pop('_stretch_words', None)
    windows = sorted([*retained.values(), *fresh], key=lambda w: w['lines'][0]['start'])
    open_windows = [window for window in windows if not window['finished']]
    for window in open_windows[:-1]:
        window['finished'] = True
    return windows
