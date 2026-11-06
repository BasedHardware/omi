#!/usr/bin/env python3
"""Import closed Gate T judgments without changing archived word clocks.

Private artifacts only. Review-group IDs are never automatic speaker identities.
"""

import argparse
import json
import math
import os
from pathlib import Path

EXCLUDED = {'', 'unsure', 'noise', 'mixed', 'not speech', 'not_speech', 'not speech / noise'}


def private_dir(path):
    path = Path(path).expanduser().resolve()
    if any((parent / '.git').exists() for parent in (path, *path.parents)):
        raise ValueError('private output must be outside a Git checkout')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def write_private(path, value, *, jsonl=False):
    path = Path(path)
    private_dir(path.parent)
    temporary = path.with_suffix(path.suffix + '.tmp')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(temporary, flags, 0o600)
    with os.fdopen(fd, 'w') as stream:
        if jsonl:
            stream.write(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in value))
        else:
            json.dump(value, stream, ensure_ascii=False)
    temporary.chmod(0o600)
    temporary.replace(path)


def scorable(label):
    return isinstance(label, str) and label.strip().lower() not in EXCLUDED


def finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('nonfinite clock')
    return value


def make_segments(words, *, max_seconds=10.0, gap_seconds=2.0):
    """Cut review clips at diarizer changes, gaps, or bounded embedding duration."""
    segments = []
    first = 0
    for index in range(1, len(words) + 1):
        split = index == len(words)
        if not split:
            split = (
                words[index].get('diarizer') != words[index - 1].get('diarizer')
                or words[index]['start'] - words[index - 1]['end'] >= gap_seconds
                or words[index]['end'] - words[first]['start'] > max_seconds
            )
        if split:
            start, end = words[first]['start'], words[index - 1]['end']
            segments.append({'w0': first, 'w1': index, 'start': start, 'end': end, 'short': end - start < 0.5})
            first = index
    return segments


def prepare(archive, output):
    archive = Path(archive).expanduser().resolve()
    truth = json.loads((archive / 'build' / 'truth.json').read_text())
    conversations_file = archive / 'conversations.json'
    conversations = json.loads(conversations_file.read_text()) if conversations_file.exists() else []
    media = {row['id']: str(archive / row['media']) for row in conversations if row.get('media')}
    recordings = []
    for key, labels in sorted(truth.items()):
        source = json.loads((archive / 'build' / f'conv_{key}.json').read_text())
        if len(labels) != len(source['words']):
            raise ValueError('archived truth/word count mismatch')
        words = []
        for word, label in zip(source['words'], labels):
            start, end = finite(word['s']), finite(word['e'])
            if start < 0 or end < start:
                raise ValueError('invalid archived word clock')
            # The archive's words already use the crop clock. Never subtract t0 here.
            words.append(
                {
                    'start': start,
                    'end': end,
                    'text': word['w'],
                    'truth': label if scorable(label) else None,
                    'diarizer': word.get('pyannote'),
                }
            )
        recording = {
            'id': key,
            't0': finite(source['t0']),
            'dur': finite(source['dur']),
            'clock': 'crop',
            'words': words,
            'segments': make_segments(words),
        }
        if key in media:
            recording['media'] = media[key]
        recordings.append(recording)
    artifact = {'schema_version': 1, 'reference': 'closed_gate_t', 'recordings': recordings}
    write_private(output, artifact)
    return artifact


def reserve_enrollment(words, *, minimum=6.0, maximum=10.0):
    """Freeze each voice's first clean contiguous span; excluded labels break it.

    Spans are crop-relative. The all-word automatic score keeps its denominator;
    only an explicitly separate enrollment variant may exclude intersecting words.
    """
    spans, reserved = [], set()
    first = None
    for index, word in enumerate(words):
        label = word['truth']
        if label is None:
            first = None
            continue
        if (
            first is None
            or words[first]['truth'] != label
            or (index and word['start'] - words[index - 1]['end'] >= 2.0)
        ):
            first = index
        if label in reserved:
            continue
        start = words[first]['start']
        if word['end'] - start >= minimum:
            end = min(word['end'], start + maximum)
            spans.append({'start': start, 'end': end, 'truth': label})
            reserved.add(label)
    return spans


def create_manifest(archive, audio_dirs, snapshot_dir, output):
    """Build a private frozen corpus with exact-name enrollment declarations."""
    from utils.stt.voiceprints import usable_person_voiceprint

    snapshot = Path(snapshot_dir).expanduser().resolve()
    profile_file, people_file = snapshot / 'profile.json', snapshot / 'people.json'
    profile = json.loads(profile_file.read_text())
    people = json.loads(people_file.read_text())
    if not isinstance(profile, dict) or not isinstance(people, list):
        raise ValueError('invalid local snapshot')
    # Import to a sibling artifact so neither closed labels nor their clocks mutate.
    output = Path(output).expanduser().resolve()
    reference = prepare(archive, output.parent / 'gate-t-reference.json')
    paths = [
        p.resolve()
        for directory in audio_dirs
        for p in Path(directory).expanduser().iterdir()
        if p.is_file() and p.suffix.lower() in {'.wav', '.m4a', '.mp3', '.flac', '.ogg'}
    ]
    eligible = {}
    for person in people:
        if (
            not person.get('is_dismissed')
            and usable_person_voiceprint(person)
            and person.get('id')
            and person.get('name')
        ):
            eligible.setdefault(person['name'].strip().casefold(), []).append(person)
    owner_markers = {'me', 'user', 'david', 'you', 'self'}
    all_labels = {w['truth'] for r in reference['recordings'] for w in r['words'] if w['truth'] is not None}
    owners = {label for label in all_labels if label.strip().casefold() in owner_markers}
    if len(owners) != 1:
        raise ValueError('expected one exact owner truth marker')
    owner = next(iter(owners))
    for recording in reference['recordings']:
        matches = list(dict.fromkeys(p for p in paths if recording['id'] in p.stem))
        if len(matches) != 1:
            raise ValueError('expected exactly one permitted source recording')
        recording['audio'] = str(matches[0])
        # This task's authorized corpus is explicitly declared English. Keep
        # that declaration separate from the containers' und language tags.
        recording['declared_language'] = 'en'
        table = {}
        for label in sorted({w['truth'] for w in recording['words'] if w['truth'] is not None}):
            if label == owner:
                table[label] = {'is_user': True}
            else:
                matches = eligible.get(label.strip().casefold(), [])
                if len(matches) == 1:
                    table[label] = {'person_id': matches[0]['id']}
        recording['identity_table'] = table
        recording['enrollment_spans'] = reserve_enrollment(recording['words'])
    reference.update(
        {
            'profile_file': str(profile_file),
            'people_file': str(people_file),
            'identity_policy': 'predeclared_exact_casefold_name_owner_marker',
            'enrollment_policy': 'first_clean_contiguous_6_to_10_seconds_per_voice',
            'score_denominator': 'all_scorable_words; enrollment exclusions are a separate variant',
        }
    )
    write_private(output, reference)
    return reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--archive', type=Path, default=Path.home() / '.local/share/labels/_archive/speaker-truth-2026-10'
    )
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--create-manifest', action='store_true')
    parser.add_argument('--audio-dir', type=Path, action='append', default=[])
    parser.add_argument('--snapshot-dir', type=Path)
    args = parser.parse_args()
    try:
        if args.create_manifest:
            if not args.audio_dir or args.snapshot_dir is None:
                raise ValueError('manifest requires explicit permitted audio directories and snapshot')
            result = create_manifest(args.archive, args.audio_dir, args.snapshot_dir, args.output)
        else:
            result = prepare(args.archive, args.output)
    except Exception:
        parser.exit(1, 'BLOCKED: Gate T preparation failed; inspect private inputs locally\n')
    print(
        json.dumps(
            {
                'recordings': len(result['recordings']),
                'words': sum(len(r['words']) for r in result['recordings']),
                'scorable_words': sum(scorable(w['truth']) for r in result['recordings'] for w in r['words']),
            }
        )
    )


if __name__ == '__main__':
    main()
