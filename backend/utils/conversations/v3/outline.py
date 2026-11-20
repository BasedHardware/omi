"""Recorded-clock line placement, de-duplication, stretch fingerprints and outlines.

Engine carried from d5798e416a6; no episode/daypart policy or persistence.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from utils.speakers.display import outline_speaker_labels


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def playback_origin(audio_file, recording):
    value = audio_file.get('playback_start')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc)
    stamps = audio_file.get('chunk_timestamps') or []
    return utc(audio_file.get('started_at')) or (
        datetime.fromtimestamp(min(stamps), timezone.utc) if stamps else utc(recording.get('started_at'))
    )


SYSTEM_PROMPT = """You outline one stretch of a person's day. The person wears an audio recorder.

The transcript comes from a small microphone worn all day. It has recognition errors. Speaker labels are unreliable: ME is the wearer when the system recognised their voice, and one other person is often split across many S-numbers. The microphone also picks up television, films, music, podcasts and strangers.

You get the complete transcript of the stretch with numbered lines. Split it into conversations, in order, and their subjects as sections. A change of people, place or activity starts a conversation. Dictation to software is its own conversation. An event at one place (talk, panel, class, appointment or visit) is ONE conversation; a live talk is conversation, not media. A tangent is a section, not a conversation. {silence_boundary} of recorded silence is a hard boundary, even if the same people or topic return. Set resumes_previous only to continue the same activity with the same people before that silence boundary. Never infer continuity merely from a similar topic. Nothing runs past two hours: give subject boundaries so the caller can cut near the middle.

Return one JSON object: {"conversations": [ ... ]} where each conversation has
- "first_line": the number of its first line. The first chapter starts at line 1.
- "title": at most 7 words, specific: the actual subject, names, places. Not "Conversation" or "Discussion".
- "line": one sentence of at most 25 words: the single most useful thing to know about this chapter (the decision, the plan, the point). Call the wearer "you". Never mention speaker labels, never quote the transcript, never comment on the notes or on your own decision. For media and background, just say what it is. Empty string if there is nothing worth saying.
- "kind": one of
  "conversation": the wearer talking with people who are present or on a call;
  "voice_work": the wearer dictating to or instructing software or an AI tool, or thinking aloud alone;
  "media": television, film, music, a podcast, a video or an audiobook (scripted or broadcast speech);
  "background": other people's talk that the wearer is not part of, or fragments too thin to tell.
- "people": names that are actually spoken or evident, else [].
- "emoji": one subject emoji.
- "sections": ordered subjects, each {"first_line": integer, "title": at most 7 words}.
- "resumes_previous": boolean, false unless the preceding conversation is explicitly continued.
Write in English unless the speech is mostly in another language."""

SILENCE = timedelta(minutes=5)
# A silence gap longer than this default (CONVERSATIONS_V3_SILENCE_GAP_SECONDS) cuts at sit-downs: the
# outline sees pauses as marker lines and finds sit-downs instead of treating silence as a hard boundary.
GAP_MARK = timedelta(minutes=2)

HARD_BOUNDARY_RULE = (
    '{silence_boundary} of recorded silence is a hard boundary, even if the same people or topic return. '
    'Set resumes_previous only to continue the same activity with the same people before that silence boundary.'
)
SITDOWN_RULE = (
    'Find the sit-downs first: stretches where the wearer is with the same people in the same place. '
    'A pause marked "min without speech", a new topic or a tangent does not end a sit-down; '
    'people leaving or arriving, a call ending, or getting up to go somewhere else does. '
    'Unclear, garbled or foreign-language lines between the lines of a sit-down belong to it: use "background" '
    'only for a stretch in which the wearer takes no part from start to finish. '
    'Set resumes_previous only to continue the same activity with the same people.'
)


def sitdown(silence_gap):
    """Sit-down cutting applies whenever the silence gap is longer than the five-minute default."""
    return silence_gap > SILENCE


# Clock slack when matching the same speech captured by two recordings.
DUPLICATE_OVERLAP_SLACK = timedelta(seconds=2)


def group_rids(group):
    return {line['conversation_id'] for line in group['lines']}


def stretches(members, now, *, silence_gap=SILENCE, lock_delay=SILENCE, settle_on_landing=False):
    lines = []
    seen = []
    for row in sorted(
        members, key=lambda r: (utc(r.get('started_at')) or utc(r.get('recorded_start')) or now, r['id'])
    ):
        origin = utc(row.get('started_at')) or utc(row.get('recorded_start'))
        if origin is None:
            continue
        for segment in row.get('transcript_segments') or []:
            text = str(segment.get('text') or '').strip()
            if not text:
                continue
            start = origin + timedelta(seconds=float(segment.get('start') or 0))
            end = origin + timedelta(seconds=max(float(segment.get('end') or 0), float(segment.get('start') or 0)))
            normalized = ' '.join(text.casefold().split())
            # Only duplicate capture is dropped: the same speech recorded by another recording at an
            # overlapping time. A speaker repeating a sentence within one recording is real speech.
            if any(
                rid != row['id']
                and start <= o_end + DUPLICATE_OVERLAP_SLACK
                and end >= o_start - DUPLICATE_OVERLAP_SLACK
                and (
                    normalized == old
                    or (
                        min(len(normalized.split()), len(old.split())) >= 6
                        and SequenceMatcher(None, normalized, old).ratio() >= 0.92
                    )
                )
                for old, o_start, o_end, rid in seen
                if abs((start - o_start).total_seconds()) <= 20
            ):
                continue
            seen.append((normalized, start, end, row['id']))
            if any(start < utc(span['end']) and end > utc(span['start']) for span in row.get('deleted_spans') or []):
                continue
            speaker = (
                'ME'
                if segment.get('is_user')
                else str(segment.get('person_name') or segment.get('speaker') or 'Speaker')
            )
            lines.append(
                {
                    'start': start,
                    'end': end,
                    'text': text,
                    'speaker': speaker,
                    'conversation_id': row['id'],
                    'segment': dict(segment),
                }
            )
    lines.sort(key=lambda line: (line['start'], line['conversation_id']))
    groups = []
    cuts = iter(sorted(utc(r['finished_at']) for r in members if r.get('v3_manual_end') and r.get('finished_at')))
    cut = next(cuts, None)
    for line in lines:
        previous = groups[-1] if groups else None
        # A segment belongs to the side on which it starts, even if it crosses the cut.
        while cut is not None and cut <= line['start']:
            if previous and previous['lines'][0]['start'] < cut:
                previous['manual_end'] = True
            cut = next(cuts, None)
        silence = previous is None or line['start'] - previous['end'] >= silence_gap
        if silence or (previous and previous['manual_end']):
            key = hashlib.sha256(f"{line['conversation_id']}:{line['start'].isoformat()}".encode()).hexdigest()[:24]
            groups.append(
                {
                    'key': key,
                    'end': line['end'],
                    'lines': [],
                    'manual_end': False,
                    'after_manual_end': bool(previous and previous['manual_end'] and not silence),
                }
            )
        group = groups[-1]
        group['lines'].append(line)
        group['end'] = max(group['end'], line['end'])
    if groups and cut is not None and cut <= now:
        groups[-1]['manual_end'] = True
    for index, group in enumerate(groups):
        # A later stretch begins only after recorded silence or a manual cut, so only the last one can
        # still be open. Page continuation and future-dated speech must not also hold an earlier one
        # open: two open stretches never commit (multiple_open_conversations parks the owner).
        later = index + 1 < len(groups)
        continues = not later and any(
            r.get('_v3_page_continues') and r['id'] == group['lines'][-1]['conversation_id'] for r in members
        )
        # Under custom timing, lock age counts from the later of the last speech and when it landed:
        # an offline batch whose speech is already old must not lock the moment it arrives, or each
        # later batch appends a fresh card behind it.
        rids = group_rids(group)
        landed = [
            r['v3_speech_landed_at']
            for r in members
            if r['id'] in rids and isinstance(r.get('v3_speech_landed_at'), datetime)
        ]
        group['settle_from'] = max([group['end'], *landed]) if settle_on_landing else group['end']
        age = now - group['settle_from']
        group['locked'] = (age >= lock_delay and not continues) or group['manual_end']
        group['finished'] = later or group['locked']
        group['outline_ready'] = group['finished'] or (age >= silence_gap and not continues)
        group['fingerprint'] = hashlib.sha256(
            json.dumps(
                [{k: line[k] for k in ('start', 'end', 'text', 'conversation_id')} for line in group['lines']],
                default=str,
                sort_keys=True,
            ).encode()
        ).hexdigest()
    return groups


def wanted(groups, cache):
    stored = {row['key']: row for row in cache}
    return [
        group
        for group in groups
        if not (group['key'] in stored and (stored[group['key']].get('fingerprint') == group['fingerprint']))
    ]


def _line_anchors(lines):
    counts = {}
    for line in lines:
        segment_id = line.get('segment', {}).get('id')
        if isinstance(segment_id, (str, int)) and segment_id != '':
            key = (line['conversation_id'], 'segment', segment_id)
        else:
            key = (line['conversation_id'], 'start', line['start'].isoformat())
        occurrence = counts.get(key, 0)
        counts[key] = occurrence + 1
        yield json.dumps([*key, occurrence], separators=(',', ':'))


def _section_line(section):
    value = section.get('first_line') if isinstance(section, dict) else None
    return value if type(value) is int else None


def preview_anchors(group, entries):
    """Keep stable coordinates for each selected topic or section, without storing more speech."""
    anchors = list(_line_anchors(group['lines']))
    indexes = {entry['first_line'] for entry in entries}
    indexes.update(
        index
        for entry in entries
        for section in entry.get('sections') or ()
        if (index := _section_line(section)) is not None
    )
    return {str(index): anchors[index - 1] for index in indexes if 1 <= index <= len(anchors)}


def matching_preview(group, previews):
    """A revision may move the stretch start. Reuse only an unambiguous anchored preview."""
    if not previews:
        return None
    anchors = set(_line_anchors(group['lines']))
    scores = {key: len(anchors.intersection(preview['anchors'].values())) for key, preview in previews.items()}
    best = max(scores.values(), default=0)
    matches = [key for key, score in scores.items() if score == best and best > 0]
    return matches[0] if len(matches) == 1 else None


def reuse_preview(group, preview):
    """Rebase the existing outline when revisions or late speech change line numbers."""
    positions = {anchor: index for index, anchor in enumerate(_line_anchors(group['lines']), 1)}
    moved = {int(index): positions.get(anchor) for index, anchor in preview['anchors'].items()}
    entries = []
    for entry in preview['entries']:
        position = moved.get(entry['first_line'])
        if position is None or (entries and position <= entries[-1]['first_line']):
            continue
        first = position if entries else 1
        sections = []
        for section in entry.get('sections') or ():
            index = _section_line(section)
            position = moved.get(index) if index is not None else None
            if position is not None and position >= first:
                sections.append({**section, 'first_line': position})
        entries.append({**entry, 'first_line': first, 'sections': sections})
    # Drop rebased sections that now belong to a different topic.
    for entry, following in zip(entries, entries[1:]):
        entry['sections'] = [
            section for section in entry['sections'] if section['first_line'] < following['first_line']
        ]
    return entries or fallback(group)


def _with_gap_marks(lines, rendered):
    out, previous_end = [], None
    for line, text in zip(lines, rendered):
        if previous_end is not None and line['start'] - previous_end >= GAP_MARK:
            out.append(f"---- {round((line['start'] - previous_end).total_seconds() / 60)} min without speech ----")
        out.append(text)
        previous_end = line['end'] if previous_end is None else max(previous_end, line['end'])
    return out


def messages(group, tz, *, cohesion=False, silence_gap=SILENCE):
    lines = group['lines']
    if cohesion:
        labels = outline_speaker_labels([line['segment'] for line in lines])
        correction = (
            '\nS1, S2 and so on are diarization labels, not names. S? marks unassigned speech. '
            'S? can refer to different people and does not by itself mark a change of people. Omi denotes the assistant.'
        )
    else:
        labels = [line['speaker'] for line in lines]
        correction = ''
    rendered = [
        f"[L{i} {line['start'].astimezone(tz):%H:%M}] {label}: {line['text']}"
        for i, (line, label) in enumerate(zip(lines, labels), 1)
    ]
    text = '\n'.join(_with_gap_marks(lines, rendered) if sitdown(silence_gap) else rendered)
    silence = 'Five minutes' if silence_gap == SILENCE else f'{int(silence_gap.total_seconds())} seconds'
    template = SYSTEM_PROMPT.replace(HARD_BOUNDARY_RULE, SITDOWN_RULE) if sitdown(silence_gap) else SYSTEM_PROMPT
    prompt = template.replace('{silence_boundary}', silence)
    return [
        ('system', prompt + correction),
        (
            'human',
            f"Stretch {lines[0]['start'].astimezone(tz):%H:%M} to {group['end'].astimezone(tz):%H:%M}.\n\nTranscript:\n{text}",
        ),
    ]


def parse(content, group):
    data = json.loads(content)
    chapters = data['conversations']
    entries = []
    previous = 0
    for chapter in chapters:
        first = chapter['first_line']
        if isinstance(first, bool) or not isinstance(first, int) or not previous < first <= len(group['lines']):
            raise ValueError('invalid_outline_line')
        if not entries and first != 1:
            raise ValueError('missing_outline_start')
        previous = first
        line = group['lines'][first - 1]
        kind = chapter['kind']
        if kind not in {'conversation', 'voice_work', 'media', 'background'}:
            raise ValueError('invalid_outline_kind')
        entries.append(
            {
                'first_line': first,
                'started_at': line['start'].isoformat(),
                'emoji': str(chapter.get('emoji') or '💬')[:16],
                'sections': chapter.get('sections') or [],
                'resumes_previous': chapter.get('resumes_previous') is True,
                'conversation_id': line['conversation_id'],
                'title': ' '.join(str(chapter['title']).split()[:7]),
                'line': ' '.join(str(chapter.get('line') or '').split()[:25]),
                'kind': kind,
                'people': [str(name)[:100] for name in chapter.get('people', [])[:20]],
            }
        )
    if not entries:
        raise ValueError('empty_outline')
    return entries


def fallback(group):
    """Conservative bounded failure path: preserve speech and deterministic cuts."""
    return [
        {
            'first_line': 1,
            'title': ' '.join(group['lines'][0]['text'].split()[:7]),
            'line': '',
            'kind': 'conversation',
            'people': [],
            'sections': [],
            'emoji': '💬',
        }
    ]
