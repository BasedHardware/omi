"""Recorded-clock line placement, de-duplication, stretch fingerprints and outlines.

Engine carried from d5798e416a6; no episode/daypart policy or persistence.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher


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

You get the complete transcript of the stretch with numbered lines. Split it into conversations, in order, and their subjects as sections. A change of people, place or activity starts a conversation. Dictation to software is its own conversation. An event at one place (talk, panel, class, appointment or visit) is ONE conversation; a live talk is conversation, not media. A tangent is a section, not a conversation. Five minutes of recorded silence is a hard boundary, even if the same people or topic return. Set resumes_previous only to continue the same activity with the same people before that silence boundary. Never infer continuity merely from a similar topic. Nothing runs past two hours: give subject boundaries so the caller can cut near the middle.

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


# Clock slack when matching the same speech captured by two recordings.
DUPLICATE_OVERLAP_SLACK = timedelta(seconds=2)


def stretches(members, now):
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
    manual_cuts = [utc(r['finished_at']) for r in members if r.get('v3_manual_end') and r.get('finished_at')]
    for line in lines:
        if (
            not groups
            or line['start'] - groups[-1]['end'] >= SILENCE
            or any(groups[-1]['end'] <= cut < line['start'] for cut in manual_cuts)
        ):
            key = hashlib.sha256(f"{line['conversation_id']}:{line['start'].isoformat()}".encode()).hexdigest()[:24]
            groups.append({'key': key, 'end': line['end'], 'lines': []})
        group = groups[-1]
        group['lines'].append(line)
        group['end'] = max(group['end'], line['end'])
    for index, group in enumerate(groups):
        next_start = (
            groups[index + 1]['lines'][0]['start'] if index + 1 < len(groups) else now + timedelta(microseconds=1)
        )
        group['manual_end'] = any(group['lines'][0]['start'] <= cut < next_start for cut in manual_cuts)
        continues = any(
            r.get('_v3_page_continues') and r['id'] == group['lines'][-1]['conversation_id'] for r in members
        )
        group['finished'] = (now - group['end'] >= SILENCE and not continues) or group['manual_end']
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


def messages(group, tz):
    lines = group['lines']
    text = '\n'.join(
        f"[L{i} {line['start'].astimezone(tz):%H:%M}] {line['speaker']}: {line['text']}"
        for i, line in enumerate(lines, 1)
    )
    return [
        ('system', SYSTEM_PROMPT),
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
