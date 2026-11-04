#!/usr/bin/env python3
"""Build blinded decision-mill pairs from persisted production-path artifacts.

Input runs: {recordings: [{id, status: "ok", clock: "crop"|"capture",
provenance: {production_path: true, ...}, turns: [{start,end,text,speaker,
person_id?,is_user?}]}]}. No synthesized fallback is permitted. Missing production
results leave the whole task pending rather than presenting a partial comparison.
"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

if __package__:
    from .prep_speaker_task import finite, private_dir, write_private
else:
    from prep_speaker_task import finite, private_dir, write_private

DEFAULT_TASK = Path.home() / '.local/share/labels/local-quality-2026-10'
DEFAULT_LETTERS = Path.home() / '.local/share/decision-mill/tools/spec-review/letters.js'


def joined_reference(words):
    """Join only consecutive scored words of one speaker with a strict <2s gap.

    An excluded word breaks adjacency, even if its neighbors have the same name.
    """
    turns = []
    previous_scorable = False
    for word in words:
        speaker = word['truth']
        if speaker is None:
            previous_scorable = False
            continue
        if previous_scorable and turns[-1]['speaker'] == speaker and word['start'] - turns[-1]['end'] < 2.0:
            turns[-1]['end'] = max(turns[-1]['end'], word['end'])
            turns[-1]['text'] += ' ' + word['text']
        else:
            turns.append(
                {
                    'start': word['start'],
                    'end': word['end'],
                    'text': word['text'],
                    'speaker': speaker,
                    'name': speaker,
                    'is_user': False,
                }
            )
        previous_scorable = True
    return turns


def production_turns(run, offset):
    if run.get('clock') not in ('crop', 'capture'):
        raise ValueError('production artifact must declare clock')
    shift = offset if run['clock'] == 'capture' else 0
    result = []
    for turn in run['turns']:
        start, end = finite(turn['start']) - shift, finite(turn['end']) - shift
        if end < start or not isinstance(turn['text'], str):
            raise ValueError('invalid production turn')
        raw_voice = turn.get('speaker_id') if turn.get('speaker_id') is not None else turn.get('speaker')
        scope = turn.get('speaker_id_scope') or turn.get('speaker_scope') or ''
        speaker = f'{scope}:{raw_voice}' if raw_voice is not None else 'Anonymous'
        # Only persisted identity evidence is displayed. Never fit identity from truth.
        name = str(
            turn.get('display_name')
            or ('You' if turn.get('is_user') else None)
            or (f'Speaker {raw_voice}' if raw_voice is not None else 'Anonymous')
        )
        result.append(
            {
                'start': start,
                'end': end,
                'text': turn['text'],
                'speaker': speaker,
                'name': name,
                'is_user': bool(turn.get('is_user', False)),
            }
        )
    return result


def task_spec(count, *, pending=False):
    # JSON is valid YAML, and avoids an optional YAML dependency in the local tool.
    spec = {
        'id': 'local-quality-2026-10',
        'workspace': 'omi',
        'title': 'Local transcript quality comparison',
        'question': 'Which transcript has better speaker names, voice turns, and wording?',
        'instructions': 'Compare A and B against the audio. Use Side by side or Full for the complete section. '
        'Judge speaker names, voice changes, gaps, and wording. '
        'Choose A, B, Tie, or Unsure. Add a free note; select decisive text and press c '
        'to comment, tagging wrong-name, wrong-turn, missing, or wording. '
        'One variant uses an archived hand-labeled word reference, not a new ASR run.',
        'labels': [
            {'id': 'A', 'label': 'A', 'key': '1'},
            {'id': 'B', 'label': 'B', 'key': '2'},
            {'id': 'tie', 'label': 'Tie', 'key': '3'},
            {'id': 'unsure', 'label': 'Unsure', 'key': '4'},
        ],
        'fields': [{'id': 'note', 'type': 'text', 'label': 'Free note'}],
        'blind': True,
        'round_size': 20,
        'stratify': 'balanced',
        'summary': 'open',
        'decision': 'Does the local production path match the archived reference quality?',
        'enough_when': {'labels': max(count, 1)},
        'minutes_per_round': 30,
        'comment_tags': ['wrong-name', 'wrong-turn', 'missing', 'wording'],
        'models': [{'id': name, 'verdict_path': f'hidden.{name}_letter'} for name in ('production', 'reference')],
    }
    if pending:
        spec['pending'] = (
            'Waiting for real persisted local production-path output for every recording. No comparison is fabricated.'
        )
    return spec


def load(value):
    return json.loads(Path(value).read_text()) if isinstance(value, (str, Path)) else value


def build(reference, runs=None, output_dir=DEFAULT_TASK, *, section_seconds=300, letters_tool=DEFAULT_LETTERS):
    if not 0 < section_seconds <= 3600:
        raise ValueError('section duration must be positive and bounded')
    output = private_dir(output_dir)
    if (output / 'labels').exists() or (output / 'comments').exists() or (output / 'waves').exists():
        raise ValueError('refusing to rebuild a task with existing judgments')
    reference = load(reference)
    run_data = load(runs) if runs is not None else {'recordings': []}
    run_rows = run_data.get('recordings', [])
    if len({r['id'] for r in run_rows}) != len(run_rows):
        raise ValueError('duplicate production recording')
    by_id = {r['id']: r for r in run_rows}
    recordings = reference['recordings']
    if not recordings or len({r['id'] for r in recordings}) != len(recordings):
        raise ValueError('invalid reference recordings')
    ready = all(
        r['id'] in by_id
        and by_id[r['id']].get('status') == 'ok'
        and by_id[r['id']].get('provenance', {}).get('production_path') is True
        and isinstance(by_id[r['id']].get('turns'), list)
        for r in recordings
    )
    if not ready:
        write_private(output / 'task.yaml', task_spec(0, pending=True))
        write_private(output / 'items.jsonl', [], jsonl=True)
        return {'pending': True, 'items': 0, 'recordings': len(recordings)}
    cards = []
    private_provenance = {}
    for number, recording in enumerate(recordings, 1):
        run = by_id[recording['id']]
        variants = {
            'reference': joined_reference(recording['words']),
            'production': production_turns(run, recording['t0']),
        }
        private_provenance[str(number)] = {
            'recording_id': recording['id'],
            't0': recording['t0'],
            'dur': recording['dur'],
            'run': run.get('provenance', {}),
        }
        duration = finite(recording['dur'])
        if duration <= 0:
            raise ValueError('invalid recording duration')
        media = recording.get('media')
        media_src = None
        if media:
            media_path = Path(media)
            if media_path.suffix.lower() not in ('.m4a', '.mp3', '.wav', '.flac', '.ogg'):
                raise ValueError('unsupported media format')
            destination = private_dir(output / 'media') / f'recording-{number}{media_path.suffix.lower()}'
            shutil.copyfile(media_path, destination)
            destination.chmod(0o600)
            media_src = 'media/' + destination.name
        else:
            raise ValueError('audio required for transcript quality comparison')
        section = 0
        while section * section_seconds < duration:
            start = section * section_seconds
            end = min(duration, start + section_seconds)
            section += 1
            cards.append(
                {
                    'id': f'recording-{number}-section-{section}',
                    'title': f'Recording {number}, section {section}',
                    'meta': {'duration_s': end - start},
                    'stratum': f'recording-{number}',
                    'truncated': start > 0 or end < duration,
                    '_start': start,
                    '_end': end,
                    '_variants': variants,
                    '_media': media_src,
                }
            )
    # Use the installed authoritative Latin-square implementation, never per-card shuffling.
    process = subprocess.run(
        [
            'node',
            str(letters_tool),
            '--variants',
            'production,reference',
            '--ids',
            ','.join(c['id'] for c in cards),
            '--seed',
            output.name,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    mappings = {row['item_id']: row['letters'] for row in map(json.loads, process.stdout.splitlines())}
    for card in cards:
        mapping = mappings[card['id']]
        start, end = card.pop('_start'), card.pop('_end')
        variants, media_src = card.pop('_variants'), card.pop('_media')
        segments = []
        sides = []
        for letter, variant in sorted(mapping.items()):
            sides.append(
                {
                    'id': letter,
                    'label': letter,
                    'start': start,
                    'duration_s': end - start,
                    'audio': {'src': media_src, 'offset_s': start, 'label': 'Recording audio'},
                }
            )
            for turn in variants[variant]:
                if turn['end'] > start and turn['start'] < end:
                    segments.append({**turn, 'side': letter})
        card['content'] = {
            'type': 'pair',
            'sides': sides,
            'segments': segments,
            'overlap': {'start': start, 'end': end},
        }
        card['hidden'] = {'letters': mapping, **{f'{variant}_letter': letter for letter, variant in mapping.items()}}
    write_private(output / 'hidden' / 'provenance.json', private_provenance)
    write_private(output / 'items.jsonl', cards, jsonl=True)
    write_private(output / 'task.yaml', task_spec(len(cards)))
    return {'pending': False, 'items': len(cards), 'recordings': len(recordings)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--runs', type=Path)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_TASK)
    parser.add_argument('--section-seconds', type=float, default=300)
    args = parser.parse_args()
    try:
        result = build(args.reference, args.runs, args.output_dir, section_seconds=args.section_seconds)
    except Exception:
        parser.exit(1, 'BLOCKED: blinded viewer build failed; inspect private inputs locally\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
