"""Export a corpus day's speech as numbered lines: the input for drafting an ideal.

    python -m testing.pipeline_lab.ideal.packet --root ROOT --day 2026-11-18 --spec SPEC.md --out DIR

The packet holds what a careful person would need to decide the day's ideal conversations, and
nothing that would anchor them on an existing answer:

- ``lines.jsonl``: every speech segment of the day's recordings, in time order, as
  ``{line, recording, at, end, local, speaker, text, dup_of}``. ``line`` ids (``L0001``...) are the
  unit an ideal is written in.
- ``transcript.txt``: the same lines, readable, with silences of 2 min or more and recording starts
  marked.
- ``recordings.json``: short recording ids (``r001``...) with their times and word counts.
- ``context.json``: the day, its timezone, the owner's profile summary and the names of people the
  app knows. Nothing else from the profile is copied.
- ``SPEC.md``: what "ideal" means (given by the caller).

Speaker labels are normalized: ``ME`` for the wearer, a known person's name, ``S1``/``S2``... for
diarized voices (numbered per recording: S1 in one recording is not S1 in another), and ``S?`` for
batch diarization's per-segment abstention (``BATCH_UNASSIGNED_*``). The same speech captured by two
overlapping recordings is kept once; the copy carries ``dup_of`` and belongs to no card.

Never included: audio, production's conversations, a replay's output, tasks or memories.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from testing.pipeline_lab.stack.io import parse_time
from testing.pipeline_lab.store import atomic_write_bytes, atomic_write_json, ensure_private_dir, read_jsonl
from testing.pipeline_lab.v3.feed import skip_reason

UNASSIGNED_PREFIX = 'BATCH_UNASSIGNED_'
DUPLICATE_WINDOW = timedelta(seconds=20)
DUPLICATE_SLACK = timedelta(seconds=2)
GAP_MARK = timedelta(minutes=2)


def _norm(text: str) -> str:
    return ' '.join(str(text or '').casefold().split())


def _duplicate(a: str, b: str) -> bool:
    if a == b:
        return True
    return min(len(a.split()), len(b.split())) >= 6 and SequenceMatcher(None, a, b).ratio() >= 0.92


def speaker_label(segment: Mapping[str, Any], local_numbers: dict[str, int], people: Mapping[str, str]) -> str:
    if segment.get('is_user'):
        return 'ME'
    person = people.get(str(segment.get('person_id') or ''))
    if person:
        return person
    raw = str(segment.get('speaker') or segment.get('speaker_name') or '')
    if not raw or raw.startswith(UNASSIGNED_PREFIX):
        return 'S?'
    if raw not in local_numbers:
        local_numbers[raw] = len(local_numbers) + 1
    return f'S{local_numbers[raw]}'


def build_lines(
    recordings: Iterable[Mapping[str, Any]], *, tz: ZoneInfo, people: Mapping[str, str] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(lines, recordings)`` for the packet; see the module docstring for the shapes."""
    people = dict(people or {})
    kept = [r for r in recordings if skip_reason(r) is None and r.get('transcript_segments')]
    kept.sort(key=lambda r: (str(r.get('started_at')), str(r.get('id'))))
    raw_lines: list[dict[str, Any]] = []
    recs: list[dict[str, Any]] = []
    for index, row in enumerate(kept, start=1):
        short = f'r{index:03d}'
        origin = parse_time(row.get('started_at'))
        if origin is None:
            continue
        numbers: dict[str, int] = {}
        words = 0
        for segment in sorted(
            row.get('transcript_segments') or [], key=lambda s: (float(s.get('start') or 0), float(s.get('end') or 0))
        ):
            text = ' '.join(str(segment.get('text') or '').split())
            if not text:
                continue
            start = origin + timedelta(seconds=float(segment.get('start') or 0))
            end = origin + timedelta(seconds=max(float(segment.get('end') or 0), float(segment.get('start') or 0)))
            words += len(text.split())
            raw_lines.append(
                {
                    'recording': short,
                    'at': start,
                    'end': end,
                    'speaker': speaker_label(segment, numbers, people),
                    'text': text,
                }
            )
        recs.append(
            {
                'recording': short,
                'recording_id': str(row['id']),
                'started_at': origin.isoformat(),
                'finished_at': str(row.get('finished_at') or ''),
                'words': words,
            }
        )
    raw_lines.sort(key=lambda line: (line['at'], line['recording']))
    lines: list[dict[str, Any]] = []
    for number, line in enumerate(raw_lines, start=1):
        lid = f'L{number:04d}'
        normalized = _norm(line['text'])
        dup_of = None
        for other in reversed(lines):
            if line['at'] - other['_at'] > DUPLICATE_WINDOW:
                break
            if (
                other['recording'] != line['recording']
                and other['dup_of'] is None
                and line['at'] <= other['_end'] + DUPLICATE_SLACK
                and line['end'] >= other['_at'] - DUPLICATE_SLACK
                and _duplicate(normalized, other['_norm'])
            ):
                dup_of = other['line']
                break
        lines.append(
            {
                'line': lid,
                'recording': line['recording'],
                'at': line['at'].isoformat(),
                'end': line['end'].isoformat(),
                'local': line['at'].astimezone(tz).strftime('%H:%M:%S'),
                'speaker': line['speaker'],
                'text': line['text'],
                'dup_of': dup_of,
                '_at': line['at'],
                '_end': line['end'],
                '_norm': normalized,
            }
        )
    for line in lines:
        for key in ('_at', '_end', '_norm'):
            line.pop(key)
    return lines, recs


def render_transcript(lines: Sequence[Mapping[str, Any]]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    previous_end: datetime | None = None
    for line in lines:
        at = datetime.fromisoformat(line['at'])
        if previous_end is not None and at - previous_end >= GAP_MARK:
            minutes = round((at - previous_end).total_seconds() / 60)
            out.append(f'        ---- {minutes} min without speech ----')
        if line['recording'] not in seen:
            seen.add(line['recording'])
            out.append(f'        [{line["recording"]} starts]')
        dup = f' (duplicate of {line["dup_of"]})' if line['dup_of'] else ''
        out.append(f'{line["line"]} {line["local"]} [{line["recording"]}] {line["speaker"]}: {line["text"]}{dup}')
        end = datetime.fromisoformat(line['end'])
        previous_end = end if previous_end is None else max(previous_end, end)
    return '\n'.join(out) + '\n'


def people_names(rows: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    return {str(r['id']): str(r['name']) for r in rows if r.get('id') and r.get('name') and not r.get('is_dismissed')}


def build_packet(root: Path, day_id: str, spec: Path, out: Path) -> dict[str, Any]:
    root = Path(root)
    corpus = root / 'corpus' / day_id
    day = json.loads((corpus / 'day.json').read_text(encoding='utf-8'))
    tz = ZoneInfo(day.get('timezone') or 'UTC')
    people = people_names(read_jsonl(corpus / 'start_state' / 'people.jsonl'))
    meta = json.loads((corpus / 'start_state' / 'meta.json').read_text(encoding='utf-8'))
    profile = ((meta.get('profile') or {}).get('ai_user_profile') or {}).get('profile_text') or ''
    lines, recordings = build_lines(read_jsonl(corpus / 'v3' / 'recordings.jsonl'), tz=tz, people=people)
    out = ensure_private_dir(Path(out))
    atomic_write_bytes(
        out / 'lines.jsonl', ''.join(json.dumps(line, ensure_ascii=False) + '\n' for line in lines).encode('utf-8')
    )
    atomic_write_bytes(out / 'transcript.txt', render_transcript(lines).encode('utf-8'))
    atomic_write_json(out / 'recordings.json', recordings)
    atomic_write_json(
        out / 'context.json',
        {
            'day': day.get('date') or day_id,
            'timezone': str(tz),
            'window': day.get('window'),
            'profile_summary': profile,
            'known_people': sorted(set(people.values())),
        },
    )
    atomic_write_bytes(out / 'SPEC.md', Path(spec).read_bytes())
    manifest = {
        'day': day_id,
        'lines': len(lines),
        'duplicates': sum(1 for line in lines if line['dup_of']),
        'recordings': len(recordings),
        'words': sum(r['words'] for r in recordings),
    }
    atomic_write_json(out / 'manifest.json', manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.ideal.packet')
    parser.add_argument('--root', required=True)
    parser.add_argument('--day', required=True)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build_packet(Path(args.root), args.day, Path(args.spec), Path(args.out))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
